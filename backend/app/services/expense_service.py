# ============================================================================
# 经费报销 Service 层
# ----------------------------------------------------------------------------
# 业务功能：项目负责人提交经费报销，依次经导师、学院、财务三级审批；终审通过后
#           把报销金额回写到项目与预算科目的“已用金额”，并提供报销列表与汇总统计。
# 核心表：
#   proj_expense   报销单主表（状态机、金额、申请人、预算科目、驳回原因）
#   proj_project   项目表（总预算 budget_amount、已用 used_amount、负责人 leader_id）
#   proj_budget    预算科目表（科目额度 budget_amount、已用 used_amount）
#   sys_attachment 报销凭证附件（biz_type="expense"，biz_id 指向报销单 id）
# 上游路由：app/api/v1/expense.py（报销申请/审批/列表/汇总）
# 下游依赖：app.schemas.project 中的报销状态常量、app.core.security 超管判定、
#           app.core.exceptions 的业务异常与权限异常。
# 关键约束：
#   1) 仅项目负责人可提交本项目报销，超级管理员可代操作；
#   2) 提交时同时校验“项目总余额”和“预算科目余额”，任一不足即拒绝；
#   3) 除已驳回外，所有状态的金额都视为已占用额度，驳回即释放占用；
#   4) 审批加行级锁串行化，只有终审通过才落账 used_amount，避免重复累加；
#   5) 报销单只做软删除（is_deleted=1），不做物理删除。
# ============================================================================
from typing import Optional, Tuple
from decimal import Decimal
from datetime import datetime
from uuid import uuid4

from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from app.models import ProjExpense, ProjProject, ProjBudget, SysAttachment
from app.schemas.project import (
    ExpenseCreate, ExpenseListItem, ExpenseSummary,
    EXPENSE_STATUS_DRAFT,
    EXPENSE_STATUS_PENDING_ADVISOR,
    EXPENSE_STATUS_ADVISOR_APPROVED,
    EXPENSE_STATUS_PENDING_COLLEGE,
    EXPENSE_STATUS_COLLEGE_APPROVED,
    EXPENSE_STATUS_PENDING_FINANCE,
    EXPENSE_STATUS_COMPLETED,
    EXPENSE_STATUS_REJECTED,
)
from app.core.exceptions import BizException, PermissionDeniedException
from app.core.security import is_super_admin

# 审批状态 → 中文显示文本
EXPENSE_STATUS_MAP = {
    EXPENSE_STATUS_DRAFT: "草稿",
    EXPENSE_STATUS_PENDING_ADVISOR: "待导师审批",
    EXPENSE_STATUS_ADVISOR_APPROVED: "导师审批通过",
    EXPENSE_STATUS_PENDING_COLLEGE: "待学院审批",
    EXPENSE_STATUS_COLLEGE_APPROVED: "学院审批通过",
    EXPENSE_STATUS_PENDING_FINANCE: "待财务审批",
    EXPENSE_STATUS_COMPLETED: "已完成",
    EXPENSE_STATUS_REJECTED: "已驳回",
}

# 可推进状态 → 推进后的下一状态（状态机单向，不允许回退）
# 完整链路：草稿 → 待导师审批 → 导师通过 → 待学院审批 → 学院通过 → 待财务审批
#          → 已完成；任意中间态被驳回后进入“已驳回”终态并释放预算占用。
# 注：草稿不会由本服务产生（创建即提交），保留该映射用于兼容历史数据/内部补录。
_NEXT_STATUS = {
    EXPENSE_STATUS_DRAFT: EXPENSE_STATUS_PENDING_ADVISOR,
    EXPENSE_STATUS_PENDING_ADVISOR: EXPENSE_STATUS_ADVISOR_APPROVED,
    EXPENSE_STATUS_ADVISOR_APPROVED: EXPENSE_STATUS_PENDING_COLLEGE,
    EXPENSE_STATUS_PENDING_COLLEGE: EXPENSE_STATUS_COLLEGE_APPROVED,
    EXPENSE_STATUS_COLLEGE_APPROVED: EXPENSE_STATUS_PENDING_FINANCE,
    EXPENSE_STATUS_PENDING_FINANCE: EXPENSE_STATUS_COMPLETED,
}


class ExpenseService:
    """经费报销业务服务。

    所有方法均为静态方法，由路由层直接调用；除查询外，写操作在方法内部自行
    提交事务。金额一律使用 Decimal 计算，避免浮点误差导致预算校验偏差。
    """

    @staticmethod
    def paginate(
        db: Session,
        offset: int,
        limit: int,
        applicant_id: Optional[int] = None,
        status: Optional[int] = None,
        keyword: Optional[str] = None,
        college_ids: Optional[list] = None,
        project_id: Optional[int] = None,
    ) -> Tuple[list, int]:
        """分页查询报销单（管理端与学生端共用同一实现）。

        参数：
            db: 数据库会话。
            offset / limit: 分页偏移量与单页条数。
            applicant_id: 按申请人过滤；学生端通常传入当前用户 id。
            status: 按审批状态精确过滤，None 表示不限制。
            keyword: 模糊匹配报销单号 / 费用说明 / 项目名称。
            college_ids: 学院数据范围；传空列表表示当前账号无任何可见学院，
                         直接返回空结果，避免退化成“不过滤”。
            project_id: 按项目过滤（项目详情页查看报销记录时使用）。
        返回：
            (当前页报销单 ORM 列表, 符合过滤条件的总条数)。
        注意：
            项目表 JOIN 只做一次：college_ids 已 JOIN 时 keyword 分支不再重复 JOIN，
            否则 SQLAlchemy 会生成重复的连接导致列歧义。
        """
        q = db.query(ProjExpense).filter(ProjExpense.is_deleted == 0)
        if applicant_id:
            q = q.filter(ProjExpense.applicant_id == applicant_id)
        if project_id:
            q = q.filter(ProjExpense.project_id == project_id)
        if status is not None:
            q = q.filter(ProjExpense.status == status)
        # [权限] 按学院范围过滤：join Project 取 college_id
        if college_ids is not None:
            if len(college_ids) == 0:
                # 空列表表示无权限（按业务约定），直接返回空
                # 空列表 ≠ 不限制：绝不能退化为全量查询，否则会越权看到全校报销
                return [], 0
            q = q.join(ProjProject, ProjExpense.project_id == ProjProject.id).filter(
                ProjProject.college_id.in_(college_ids)
            )
        if keyword:
            kw = f"%{keyword}%"
            # 如果还没 Join Project（上面 college_ids 已 join），这里要补 join
            if college_ids is None:
                q = q.join(ProjProject, ProjExpense.project_id == ProjProject.id)
            q = q.filter(
                or_(
                    ProjExpense.expense_no.like(kw),
                    ProjExpense.expense_desc.like(kw),
                    ProjProject.project_name.like(kw),
                )
            )
        total = q.with_entities(func.count(ProjExpense.id)).scalar() or 0
        # 列表按创建时间倒序，最新提交的报销单优先展示；total 独立统计保证跨页准确
        items = q.order_by(ProjExpense.created_at.desc()).offset(offset).limit(limit).all()
        return items, total

    @staticmethod
    def to_list_item(db: Session, exp: ProjExpense) -> ExpenseListItem:
        """把单条报销单转换为列表展示项（保留旧接口）。

        参数：db 会话、报销单 ORM 对象。
        返回：ExpenseListItem，包含项目名称、状态中文名与附件列表。
        注意：内部直接复用批量转换方法，单条调用会多一次 IN 查询，
              仅为兼容旧调用方，新代码应优先使用 to_list_items。
        """
        # 单条场景：保留旧接口但尽量复用批量逻辑
        results = ExpenseService.to_list_items(db, [exp])
        return results[0]

    @staticmethod
    def to_list_items(db: Session, exps: list) -> list:
        """
        [P1-4] 批量把 Expense ORM 对象 → ExpenseListItem

        功能：为一批报销单补齐项目名称、状态中文文本和附件列表，供列表接口返回。
        参数：
            db: 数据库会话。
            exps: 报销单 ORM 列表（可为空）。
        返回：
            ExpenseListItem 列表，顺序与入参一致；空入参返回空列表。
        注意：
            项目名与附件各用一次 IN 查询批量取出，把原来的 O(N) 次单查降为常数次，
            这是列表接口避免 N+1 的关键；附件内部按上传时间升序，保证展示顺序稳定。
        """
        if not exps:
            return []
        # 用 set 去重项目 id：同一项目的多张报销单只查一次项目名
        project_ids = list({e.project_id for e in exps if e.project_id})
        project_by_id: dict = {}
        if project_ids:
            rows = db.query(ProjProject.id, ProjProject.project_name).filter(
                ProjProject.id.in_(project_ids),
                ProjProject.is_deleted == 0,
            ).all()
            project_by_id = {pid: pname for pid, pname in rows}

        out: list = []
        # 批量加载报销附件
        # 按 biz_id 分组后，转换阶段无需再查库；下载/预览统一走文件接口，避免暴露存储路径
        exp_ids = [e.id for e in exps]
        atts_by_exp: dict = {}
        if exp_ids:
            atts = db.query(SysAttachment).filter(
                SysAttachment.biz_type == "expense",
                SysAttachment.biz_id.in_(exp_ids),
                SysAttachment.is_deleted == 0,
            ).order_by(SysAttachment.created_at.asc()).all()
            for a in atts:
                atts_by_exp.setdefault(a.biz_id, []).append({
                    "id": a.id, "file_name": a.file_name, "file_size": a.file_size,
                    "file_type": a.file_type, "uploader_name": a.uploader_name,
                    "download_url": f"/api/files/download/{a.id}",
                    "preview_url": f"/api/files/preview/{a.id}",
                })
        for exp in exps:
            item = ExpenseListItem.model_validate(exp)
            proj_name = project_by_id.get(exp.project_id)
            item.project_name = proj_name
            # 状态文本统一由映射表生成；遇到历史脏状态兜底“未知”，不让接口报错
            item.status_text = EXPENSE_STATUS_MAP.get(exp.status, "未知")
            item.attachments = atts_by_exp.get(exp.id, [])
            out.append(item)
        return out

    @staticmethod
    def get_summary(
        db: Session,
        applicant_id: Optional[int] = None,
        college_ids: Optional[list] = None,
    ) -> ExpenseSummary:
        """统计报销汇总（列表页顶部的数字卡片）。

        参数：
            db: 数据库会话。
            applicant_id: 限定申请人；None 表示按数据范围统计全部。
            college_ids: 学院数据范围；空列表表示无权限，返回全零汇总。
        返回：
            ExpenseSummary：总单数、总金额、已报销金额（仅“已完成”）、待处理单数。
        注意：
            待处理包含草稿、各级待审批与各级审批通过（尚未终审）的状态，
            与前端“处理中”口径保持一致；已驳回不计入任何金额统计。
        """
        q = db.query(ProjExpense).filter(ProjExpense.is_deleted == 0)
        if applicant_id:
            q = q.filter(ProjExpense.applicant_id == applicant_id)
        if college_ids is not None:
            if len(college_ids) == 0:
                # 无权限范围 → 空汇总
                return ExpenseSummary(
                    total_count=0,
                    total_amount=Decimal("0"),
                    approved_amount=Decimal("0"),
                    pending_count=0,
                )
            q = q.join(ProjProject, ProjExpense.project_id == ProjProject.id).filter(
                ProjProject.college_id.in_(college_ids)
            )
        total_count = q.with_entities(func.count(ProjExpense.id)).scalar() or 0
        # 申请总额：包含所有未删除状态（含已驳回），用于展示“累计申请”口径
        total_amount = q.with_entities(func.coalesce(func.sum(ProjExpense.expense_amount), Decimal("0"))).scalar() or Decimal("0")
        # 已完成(已报销)金额：只有终审通过并落账的单据才计入，避免把审批中金额算作已支出
        approved_amount = q.filter(ProjExpense.status == EXPENSE_STATUS_COMPLETED).with_entities(
            func.coalesce(func.sum(ProjExpense.expense_amount), Decimal("0"))
        ).scalar() or Decimal("0")
        # 待处理：草稿 + 各级待审批 + 各级审批通过(尚未完成)
        # 与列表页“处理中”筛选口径一致，避免顶部统计数字与筛选结果对不上
        pending_count = q.filter(ProjExpense.status.in_([
            EXPENSE_STATUS_DRAFT,
            EXPENSE_STATUS_PENDING_ADVISOR,
            EXPENSE_STATUS_ADVISOR_APPROVED,
            EXPENSE_STATUS_PENDING_COLLEGE,
            EXPENSE_STATUS_COLLEGE_APPROVED,
            EXPENSE_STATUS_PENDING_FINANCE,
        ])).with_entities(
            func.count(ProjExpense.id)
        ).scalar() or 0
        return ExpenseSummary(
            total_count=total_count,
            total_amount=total_amount,
            approved_amount=approved_amount,
            pending_count=pending_count,
        )

    @staticmethod
    def create(db: Session, data: ExpenseCreate, operator) -> ProjExpense:
        """提交一张报销单（创建即进入待导师审批，不存在草稿态）。

        参数：
            db: 数据库会话。
            data: 报销申请表单（项目 id、金额、说明、发票号、预算科目、附件 id 列表）。
            operator: 当前登录用户，作为申请人。
        返回：
            新建并已刷新 id 的 ProjExpense 对象。
        权限：
            仅项目负责人可为本项目提交报销；超级管理员可代任意项目提交。
        异常：
            项目不存在 → BizException；
            非负责人 → PermissionDeniedException；
            超出项目预算 / 科目预算 / 科目不属于项目 → BizException。
        副作用：
            1) 生成全局唯一报销单号；
            2) 将本人上传的临时附件（biz_type=expense、biz_id=0）绑定到本单；
            3) 提交事务，确保报销单与附件绑定同时生效。
        """
        applicant_id = operator.id
        applicant_name = operator.real_name or operator.username
        project = db.query(ProjProject).filter(
            ProjProject.id == data.project_id, ProjProject.is_deleted == 0
        ).first()
        if not project:
            raise BizException("项目不存在")
        # [权限] 仅项目负责人（超级管理员可代操作）可提交该项目的报销申请
        if not is_super_admin(operator) and project.leader_id != operator.id:
            raise PermissionDeniedException(message="仅项目负责人可提交该项目的报销申请")
        # [预算双重校验] 先校验项目总余额，再校验预算科目余额：
        # 项目总额是硬上限，科目额度是内部细分上限，两者任一不足都不允许提交。
        # 占用口径：除“已驳回”外的全部状态都占用额度，因此审批中的单据不会被重复申请。
        # [预算] 报销金额不得超过项目剩余预算；
        # 已提交/审批中的费用视为已占用，已驳回的释放额度
        budget = Decimal(project.budget_amount or 0)
        # 项目未配置预算时按 0 处理，任何正金额都会被拒绝，避免“无预算可无限报销”
        occupied = db.query(
            func.coalesce(func.sum(ProjExpense.expense_amount), 0)
        ).filter(
            ProjExpense.project_id == project.id,
            ProjExpense.is_deleted == 0,
            ProjExpense.status != EXPENSE_STATUS_REJECTED,
        ).scalar() or Decimal("0")
        amount = Decimal(data.expense_amount or 0)
        remaining = budget - Decimal(occupied)
        if amount > remaining:
            raise BizException(f"报销金额超出剩余预算（剩余 {remaining} 元）")

        # [预算科目] 指定预算科目时，额外校验该科目剩余额度，避免单科目超支
        if data.budget_item_id:
            budget_row = db.query(ProjBudget).filter(
                ProjBudget.id == data.budget_item_id,
                ProjBudget.project_id == project.id,
                ProjBudget.is_deleted == 0,
            ).first()
            if not budget_row:
                raise BizException("所选预算科目不存在或不属于该项目")
            item_occupied = db.query(
                func.coalesce(func.sum(ProjExpense.expense_amount), 0)
            ).filter(
                ProjExpense.budget_item_id == budget_row.id,
                ProjExpense.is_deleted == 0,
                ProjExpense.status != EXPENSE_STATUS_REJECTED,
            ).scalar() or Decimal("0")
            item_remaining = Decimal(budget_row.budget_amount or 0) - Decimal(item_occupied)
            if amount > item_remaining:
                raise BizException(
                    f"报销金额超出该预算科目剩余额度"
                    f"（科目「{budget_row.budget_item}」剩余 {item_remaining} 元）"
                )

        # 单号加入微秒 + 随机后缀，避免同一申请人同一秒内两次提交撞唯一键
        expense_no = (
            f"EXP{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
            f"{uuid4().hex[:4].upper()}"
        )
        exp = ProjExpense(
            expense_no=expense_no,
            project_id=data.project_id,
            applicant_id=applicant_id,
            applicant_name=applicant_name,
            expense_amount=data.expense_amount,
            expense_desc=data.expense_desc,
            invoice_no=data.invoice_no,
            budget_item_id=data.budget_item_id,
            # 创建即提交，直接进入第一级审批；草稿态仅保留给历史数据兼容
            status=EXPENSE_STATUS_PENDING_ADVISOR,
            submit_time=datetime.now(),
        )
        db.add(exp)
        # 先 flush 取得自增 id 才能绑定附件；此处不提交，失败时整个事务一起回滚
        db.flush()  # 先落库取得 exp.id
        # 关联上传的临时附件（biz_id=0 → 当前报销单 id）
        # 绑定条件同时限制 biz_type / biz_id=0 / uploader_id，防止把他人附件或已绑定附件挂到本单
        if data.attachment_ids:
            db.query(SysAttachment).filter(
                SysAttachment.id.in_(data.attachment_ids),
                SysAttachment.biz_type == "expense",
                SysAttachment.biz_id == 0,
                SysAttachment.uploader_id == applicant_id,  # 仅可绑定本人上传的临时附件
                SysAttachment.is_deleted == 0,
            ).update({SysAttachment.biz_id: exp.id}, synchronize_session=False)
        # 单次提交：避免"报销单已提交但附件未绑定"的半成品状态
        db.commit()
        db.refresh(exp)
        return exp

    @staticmethod
    def review(db: Session, expense_id: int, approved: bool, opinion: Optional[str] = None) -> ProjExpense:
        """审批报销单：通过则推进到下一审批阶段，不通过则整单驳回。

        参数：
            db: 数据库会话。
            expense_id: 报销单 id。
            approved: True 表示审批通过；False 表示驳回。
            opinion: 审批意见；驳回时写入 reject_reason，通过时清空历史驳回原因。
        返回：
            更新后的 ProjExpense 对象。
        异常：
            单据不存在 / 已处于终态 / 当前状态无法推进 → BizException。
        副作用：
            终审通过（待财务 → 已完成）时，同时累加项目和对应预算科目的 used_amount，
            并记录审批时间；驳回时只改状态与原因，不落账。
        注意：
            方法内使用 SELECT ... FOR UPDATE 行级锁，必须与调用方处于同一事务中，
            commit 之后锁才释放；并发重复审批会在锁上排队，第二个请求会读到终态而报错。
        """
        # 行级锁：串行化同一报销单的并发审批，避免重复审批与额度重复回写
        # 锁随本方法末尾的 commit 释放，因此审批过程中不得提前提交事务
        exp = db.query(ProjExpense).filter(
            ProjExpense.id == expense_id, ProjExpense.is_deleted == 0
        ).with_for_update().first()
        if not exp:
            raise BizException("报销记录不存在")

        # 终态保护：已完成/已驳回不允许再次审批，防止终审被重复触发导致 used_amount 重复累加
        if exp.status in (EXPENSE_STATUS_COMPLETED, EXPENSE_STATUS_REJECTED):
            raise BizException("该报销记录已终审，不可再次审批")

        if not approved:
            # 驳回是终态：占用额度按“非驳回状态”统计，改状态后自动释放，无需回退金额
            exp.status = EXPENSE_STATUS_REJECTED
            if opinion:
                exp.reject_reason = opinion
            exp.approval_time = datetime.now()
        else:
            # 通过 → 推进到下一阶段
            # 严格按状态映射前进一步，不允许跳级审批；到达“已完成”即触发终审落账
            next_status = _NEXT_STATUS.get(exp.status)
            if next_status is None:
                raise BizException(f"当前状态({EXPENSE_STATUS_MAP.get(exp.status, '?')})不可推进")
            exp.status = next_status
            exp.reject_reason = None
            if next_status == EXPENSE_STATUS_COMPLETED:
                exp.approval_time = datetime.now()
                # 终审完成：回写已使用金额（项目总额 + 对应预算科目），避免预算占用统计失真
                # 行级锁：并发终审时串行化读改写，防止 used_amount 丢失更新；
                # 项目与预算科目分别加锁，二者互不影响，避免跨单据并发更新互相覆盖
                amt = Decimal(exp.expense_amount or 0)
                project = db.query(ProjProject).filter(
                    ProjProject.id == exp.project_id
                ).with_for_update().first()
                if project:
                    project.used_amount = Decimal(project.used_amount or 0) + amt
                if exp.budget_item_id:
                    budget = db.query(ProjBudget).filter(
                        ProjBudget.id == exp.budget_item_id
                    ).with_for_update().first()
                    if budget:
                        budget.used_amount = Decimal(budget.used_amount or 0) + amt

        db.commit()
        db.refresh(exp)
        return exp
