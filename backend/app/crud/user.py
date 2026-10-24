"""
用户管理模块 数据访问层(CRUD)
所有数据库操作在此集中封装，路由层与服务层通过此类访问数据库

本模块包含三部分：
    - UserCRUD：sys_user 的查询、增改、软删除与登录信息更新；
    - CollegeCRUD：sys_college 的基础查询（列表用于下拉框与数据权限映射）；
    - OperationLogCRUD：sys_operation_log 的分页查询与导出。

关键设计：
    - 用户一律软删除（is_deleted=1），保留操作日志、项目负责人等历史外键引用；
    - 列表查询把 DataScope 翻译成 college_id / id 过滤，避免越权看到他人数据；
    - 排序字段走白名单，避免外部参数直接进入 SQL；
    - 密码只在写入时哈希，查询结果中的 password_hash 由上层序列化时剔除。
"""
from typing import Optional, List, Tuple
from sqlalchemy import or_, and_, func
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.core.deps import DataScope
from app.models import SysUser, SysCollege, SysOperationLog


class UserCRUD:
    """用户 CRUD 封装类。

    角色取值：1 学生 / 2 教师 / 3 专家 / 4 管理员；
    管理员再按 college_id 是否为空区分为超管与学院管理员（判断逻辑在 DataScope 中）。
    """

    # ====================================================================
    # 用户查询
    # ====================================================================
    @staticmethod
    def get_by_id(db: Session, user_id: int) -> Optional[SysUser]:
        """按主键取用户，已软删除的用户视为不存在。

        :param user_id: 用户主键
        :return: 用户对象或 None
        """
        return db.query(SysUser).filter(SysUser.id == user_id, SysUser.is_deleted == 0).first()

    @staticmethod
    def get_by_username(db: Session, username: str) -> Optional[SysUser]:
        """按登录账号取用户（登录校验与「账号是否重复」检查使用）。

        :param username: 登录账号，调用方需自行做去空格/大小写处理
        :return: 用户对象或 None；软删除账号不返回，因此可重新注册同名账号
        """
        return db.query(SysUser).filter(SysUser.username == username, SysUser.is_deleted == 0).first()

    @staticmethod
    def paginate(
        db: Session,
        *,
        offset: int = 0,
        limit: int = 10,
        keyword: Optional[str] = None,
        role: Optional[int] = None,
        college_id: Optional[int] = None,
        status: Optional[int] = None,
        data_scope: Optional[DataScope] = None,
        order_by: str = "created_at",
        order_dir: str = "desc",
    ) -> Tuple[List[SysUser], int]:
        """
        分页查询用户列表，支持多条件过滤 + 行级数据权限
        返回：(用户列表, 总条数)

        :param keyword: 模糊匹配账号/姓名/邮箱/手机号，便于管理员按任一信息找人
        :param role: 角色筛选（1/2/3/4）
        :param college_id: 学院筛选；必须与 DataScope 取交集，不能直接覆盖权限条件
        :param status: 启用(1)/禁用(0)
        :param data_scope: 超管 all=True 不过滤；学院管理员仅本院；学生仅自己
        :param order_by/order_dir: 排序字段白名单 + 方向
        :side effect: 只读，不做密码脱敏，调用方须使用不返回 password_hash 的 schema
        """
        # 软删除用户在列表、下拉、统计中都不应出现，因此作为最基础条件。
        query = db.query(SysUser).filter(SysUser.is_deleted == 0)

        # ---- 数据权限范围过滤 ----
        # all=True 仅超级管理员（role=4 且无学院归属），此时不加任何行级条件。
        if data_scope and not data_scope.scope.get("all"):
            allowed_colleges = data_scope.scope.get("college_ids")
            if allowed_colleges:
                # 学院管理员只能看到本院用户；教师也带 college_ids，因此同样收敛到本院。
                query = query.filter(SysUser.college_id.in_(allowed_colleges))
            # 学生角色只能看自己
            # 放在学院过滤之后，用 AND 叠加，防止学生借 college_id 参数看到同学。
            if data_scope.scope.get("is_student"):
                query = query.filter(SysUser.id == data_scope.user_id)

        # ---- 关键词模糊查询 ----
        # 四个字段任一命中即可；%kw% 为 contains 语义，注意前导 % 无法命中普通索引，
        # 用户表数据量不大，这里优先保证管理端检索体验。
        if keyword:
            kw = f"%{keyword}%"
            query = query.filter(or_(
                SysUser.username.like(kw),
                SysUser.real_name.like(kw),
                SysUser.email.like(kw),
                SysUser.phone.like(kw),
            ))
        # 以下筛选用 is not None 判断：status=0（禁用）是合法值，不能写成 if status。
        if role is not None:
            query = query.filter(SysUser.role == role)
        if college_id is not None:
            query = query.filter(SysUser.college_id == college_id)
        if status is not None:
            query = query.filter(SysUser.status == status)

        # 先 count 再分页：count 复用上面的过滤条件，保证总数与列表口径一致。
        total = query.with_entities(func.count(SysUser.id)).scalar() or 0

        # 排序
        # 白名单限定可排序字段，getattr 只能取到模型属性，避免 SQL 注入；
        # 非法字段回退 created_at，保证接口稳定。
        allowed_orders = {"id", "username", "real_name", "role", "college_id", "status", "created_at", "updated_at"}
        order_col = getattr(SysUser, order_by) if order_by in allowed_orders else SysUser.created_at
        order_func = order_col.desc() if order_dir == "desc" else order_col.asc()
        users = query.order_by(order_func).offset(offset).limit(limit).all()
        return users, total

    @staticmethod
    def list_by_ids(db: Session, user_ids: List[int]) -> List[SysUser]:
        """[P1-4] 按ID列表批量查询用户（消除N+1使用）

        :param user_ids: 用户主键列表
        :return: 存在的、未软删除的用户；入参为空时直接返回空列表，避免 IN ()
        :side effect: 只读。批量取回后由调用方在内存建 id->user 映射，
                      替代在循环里逐个 get_by_id 的 N+1 查询。
        """
        if not user_ids:
            return []
        return db.query(SysUser).filter(
            SysUser.id.in_(user_ids),
            SysUser.is_deleted == 0,
        ).all()

    # ====================================================================
    # 用户增删改
    # ====================================================================
    @staticmethod
    def create(db: Session, obj_in: dict) -> SysUser:
        """创建用户，自动哈希密码

        :param obj_in: 用户字段字典，可含明文 password
        :return: 已 flush、含主键的用户对象
        :side effect: 会 pop 掉 obj_in 中的 password，改写为 password_hash；
                      不落明文密码，调用方不应再复用该字典。
        """
        if "password" in obj_in:
            obj_in["password_hash"] = hash_password(obj_in.pop("password"))
        db_obj = SysUser(**obj_in)
        db.add(db_obj)
        db.flush()
        return db_obj

    @staticmethod
    def update(db: Session, db_obj: SysUser, obj_in: dict) -> SysUser:
        """更新用户，若包含password字段则自动哈希

        :param db_obj: 已加载的用户对象
        :param obj_in: 待更新字段；password 为空串/None 时视为「不修改密码」
        :return: 更新后的用户对象
        :side effect: 会 pop password；值为 None 的普通字段被跳过，
                      因此本方法无法把字段显式置空（用户表业务上也不需要）。
        """
        if "password" in obj_in and obj_in["password"]:
            obj_in["password_hash"] = hash_password(obj_in.pop("password"))
        for field, value in obj_in.items():
            if value is not None and hasattr(db_obj, field) and field != "id":
                setattr(db_obj, field, value)
        db.flush()
        return db_obj

    @staticmethod
    def soft_delete(db: Session, user_id: int) -> int:
        """软删除用户（标记is_deleted=1），返回受影响行数

        不做物理删除：项目负责人、操作日志、审核记录等仍引用该用户，
        物理删除会造成外键悬空与历史记录不可追溯。
        :param user_id: 用户主键
        :return: 受影响行数；0 表示用户不存在或已删除
        """
        rows = db.query(SysUser).filter(SysUser.id == user_id, SysUser.is_deleted == 0) \
            .update({"is_deleted": 1}, synchronize_session=False)
        db.flush()
        return rows

    @staticmethod
    def batch_update_status(db: Session, user_ids: List[int], status: int) -> int:
        """批量启/禁用用户

        :param user_ids: 目标用户主键列表
        :param status: 1 启用 / 0 禁用
        :return: 实际更新行数（已删除的用户不计入）
        :side effect: 只更新 status 字段；禁用后由鉴权层在登录/请求时拦截。
        """
        rows = db.query(SysUser).filter(SysUser.id.in_(user_ids), SysUser.is_deleted == 0) \
            .update({SysUser.status: status}, synchronize_session=False)
        db.flush()
        return rows

    # ====================================================================
    # 登录相关
    # ====================================================================
    @staticmethod
    def update_login_info(db: Session, user: SysUser, ip: str) -> None:
        """用户登录成功后，更新最后登录IP和时间

        :param user: 已通过密码校验的用户对象
        :param ip: 客户端 IP（由路由层从请求中取得，可能为代理后的真实 IP）
        :side effect: 修改 user 的 last_login_ip / last_login_at 并 flush；
                      失败不影响登录本身，调用方通常忽略异常。
        """
        from datetime import datetime
        user.last_login_ip = ip
        user.last_login_at = datetime.now()
        db.flush()


class CollegeCRUD:
    """学院 CRUD 封装类。

    学院表体量小且变动少，主要被用户/项目的数据权限与下拉选项引用；
    这里只做基础查询与维护，缓存由上层（redis_cache）负责。
    """

    @staticmethod
    def get_by_id(db: Session, college_id: int) -> Optional[SysCollege]:
        """按主键取学院，用于把 college_id 还原成名称。"""
        return db.query(SysCollege).filter(SysCollege.id == college_id).first()

    @staticmethod
    def get_by_code(db: Session, code: str) -> Optional[SysCollege]:
        """按学院编码查询（导入用户/项目时用编码换 ID）。"""
        return db.query(SysCollege).filter(SysCollege.college_code == code).first()

    @staticmethod
    def list_all(db: Session, include_disabled: bool = False) -> List[SysCollege]:
        """列出学院，默认只返回启用状态（status=1）的。

        :param include_disabled: 管理端需要维护停用学院时传 True
        :return: 按 sort_order、id 升序的学院列表，保证下拉框顺序稳定
        """
        q = db.query(SysCollege)
        if not include_disabled:
            # 停用学院不再出现在业务下拉框中，避免新数据挂到已撤销的学院。
            q = q.filter(SysCollege.status == 1)
        return q.order_by(SysCollege.sort_order.asc(), SysCollege.id.asc()).all()

    @staticmethod
    def list_by_ids(db: Session, college_ids: List[int]) -> List[SysCollege]:
        """[P1-4] 按ID列表批量查询学院（消除N+1使用）

        :param college_ids: 学院主键列表
        :return: 学院列表；入参为空返回空列表
        :side effect: 只读。用于列表序列化前一次性取回学院名，避免逐行查询。
        """
        if not college_ids:
            return []
        return db.query(SysCollege).filter(
            SysCollege.id.in_(college_ids),
        ).all()

    @staticmethod
    def create(db: Session, obj_in: dict) -> SysCollege:
        """新增学院；编码唯一性由数据库唯一索引兜底，冲突时由上层转成业务异常。"""
        obj = SysCollege(**obj_in)
        db.add(obj)
        db.flush()
        return obj

    @staticmethod
    def update(db: Session, db_obj: SysCollege, obj_in: dict) -> SysCollege:
        """更新学院字段；None 表示未填写，跳过以免覆盖成空值。"""
        for f, v in obj_in.items():
            if v is not None and hasattr(db_obj, f) and f != "id":
                setattr(db_obj, f, v)
        db.flush()
        return db_obj


class OperationLogCRUD:
    """操作日志 CRUD。

    日志表只增不改，查询面向管理端审计页：
    支持关键字、模块、操作类型、操作人、学院、时间区间与成功/失败筛选。
    """

    @staticmethod
    def paginate(
        db: Session,
        *,
        offset: int,
        limit: int,
        keyword: Optional[str] = None,
        module_name: Optional[str] = None,
        operation_type: Optional[str] = None,
        user_id: Optional[int] = None,
        college_id: Optional[int] = None,
        start_time: Optional = None,
        end_time: Optional = None,
        modules: Optional[str] = None,
        operation_types: Optional[str] = None,
        user_roles: Optional[str] = None,
        statuses: Optional[str] = None,
        order_dir: str = "desc",
    ) -> Tuple[List[SysOperationLog], int]:
        """分页查询操作日志。

        :param keyword: 模糊匹配操作人账号/姓名、描述、URL、IP
        :param module_name: 单个模块精确匹配
        :param modules: 逗号分隔的模块多选（前端筛选器传参格式）
        :param operation_type / operation_types: 单个/多选操作类型
        :param user_id: 指定操作人
        :param user_roles: 逗号分隔的角色 ID，用于「只看管理员操作」等场景
        :param statuses: success/fail 组合，决定是否按响应码过滤
        :param college_id: 学院管理员的数据范围，经 sys_user 关联到本院
        :param start_time/end_time: 操作时间闭区间
        :return: (当前页日志, 总数)
        :side effect: 只读。日志量随时间增长，必须分页，导出走 list_all_for_export 的限量口径。
        """
        # 日志不软删除，因此无需 is_deleted 条件；这是本类与其它 CRUD 的差异。
        q = db.query(SysOperationLog)
        if keyword:
            # 五个字段任一命中即可；IP 也参与检索，便于排查异常来源。
            kw = f"%{keyword}%"
            q = q.filter(or_(
                SysOperationLog.username.like(kw),
                SysOperationLog.real_name.like(kw),
                SysOperationLog.operation_desc.like(kw),
                SysOperationLog.request_url.like(kw),
                SysOperationLog.ip_address.like(kw),
            ))
        # 单值与多值参数互斥使用：前端单选走 module_name，多选走 modules。
        if module_name:
            q = q.filter(SysOperationLog.module_name == module_name)
        if modules:
            # 逗号串在此拆成 IN 列表；strip 后去空，避免出现空字符串条件。
            vals = [m.strip() for m in modules.split(",") if m.strip()]
            if vals:
                q = q.filter(SysOperationLog.module_name.in_(vals))
        if operation_type:
            q = q.filter(SysOperationLog.operation_type == operation_type)
        if operation_types:
            vals = [t.strip() for t in operation_types.split(",") if t.strip()]
            if vals:
                q = q.filter(SysOperationLog.operation_type.in_(vals))
        if user_id:
            q = q.filter(SysOperationLog.user_id == user_id)
        if user_roles:
            # 角色是整数枚举，只保留能解析为数字的项，防止非法入参导致 SQL 报错。
            vals = [int(r) for r in user_roles.split(",") if r.strip().isdigit()]
            if vals:
                q = q.filter(SysOperationLog.user_role.in_(vals))
        if statuses:
            vals = [s.strip() for s in statuses.split(",") if s.strip()]
            # 只在「仅成功」或「仅失败」时过滤：
            # 两者都选等于全部，加条件反而多余；都不选则不过滤。
            only_success = "success" in vals and "fail" not in vals
            only_fail = "fail" in vals and "success" not in vals
            if only_success:
                # 2xx 视为成功
                q = q.filter(SysOperationLog.response_code >= 200, SysOperationLog.response_code < 300)
            elif only_fail:
                # 响应码为空（请求未进入业务逻辑/异常中断）也计入失败，
                # 否则排查问题时会漏掉崩溃请求。
                q = q.filter(or_(
                    SysOperationLog.response_code.is_(None),
                    SysOperationLog.response_code < 200,
                    SysOperationLog.response_code >= 300,
                ))
        if college_id is not None:
            # 学院管理员数据范围：仅本院用户产生的日志（经 sys_user 关联所属学院）
            # 用 inner join 是有意的：无对应用户的日志（如匿名 401）不归属任何学院，
            # 学院管理员不应看到。user_id 上需有索引，否则日志量大时 join 会慢。
            q = q.join(SysUser, SysOperationLog.user_id == SysUser.id).filter(
                SysUser.college_id == college_id
            )
        if start_time:
            q = q.filter(SysOperationLog.operation_time >= start_time)
        if end_time:
            q = q.filter(SysOperationLog.operation_time <= end_time)
        # count 必须在 order_by/offset 之前，且与列表共用同一批过滤条件。
        total = q.with_entities(func.count(SysOperationLog.id)).scalar() or 0
        # 日志按时间排序最常用；order_dir 已在依赖层做过 asc/desc 归一化。
        order_col = SysOperationLog.operation_time.desc() if order_dir == "desc" \
            else SysOperationLog.operation_time.asc()
        items = q.order_by(order_col).offset(offset).limit(limit).all()
        return items, total

    @staticmethod
    def list_all_for_export(db: Session, **filters) -> List[SysOperationLog]:
        """导出用：不分页，最多导1万条

        前端导出需要「与当前筛选一致的全量数据」而非当前页：
        日志页默认按页展示，若只导出当前页会漏掉大部分记录。
        这里复用 paginate 的过滤逻辑（保证口径一致），用固定 limit=10000
        作为保护上限，避免一次导出把内存与数据库压垮。
        :param filters: 与 paginate 相同的筛选参数（offset/limit 由本方法固定）
        :return: 最多 10000 条日志
        """
        items, _ = OperationLogCRUD.paginate(db, offset=0, limit=10000, **filters)
        return items
