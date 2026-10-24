# ============================================================================
# 结项归档导出服务
# ----------------------------------------------------------------------------
# 业务功能：将已结题项目的关键信息与附件打包为 ZIP，供学院/学校留档：
#   - 项目归档信息.xlsx（项目概况 / 团队 / 预算 / 中期 / 成果 / 结项验收 / 附件清单）
#   - 附件/（项目附件、中期检查附件、成果证明材料）
# 核心表：
#   proj_project              项目主表（状态、预算、成员、成果、结项报告）
#   proj_midterm              中期检查（进展、经费使用、审核意见）
#   proj_achievement          成果（类型/级别/认定状态）
#   proj_achievement_review   成果认定记录
#   sys_attachment            附件（project/midterm/achievement 三类业务归属）
# 上游路由：app/api/v1/archive.py（项目结项归档下载）
# 下游依赖：ProjectService（详情 + 权限）、ProjectCRUD/MidtermCRUD、
#           ExcelHelper（多 sheet 导出）、Python zipfile。
# 关键约束：
#   1) 仅“已结题”项目可导出归档，其他状态直接拒绝；
#   2) 复用 ProjectService.get_detail 做数据权限校验，无权限用户无法导出；
#   3) 源文件缺失时仍写入附件清单并标注“否（源文件缺失）”，不中断打包；
#   4) 同一目录同名附件自动追加序号，避免 ZIP 内文件覆盖。
# ============================================================================
import io
import os
import re
import zipfile
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.exceptions import ParamValidateException
from app.crud.project import ProjectCRUD
from app.crud.review import MidtermCRUD
from app.models import (
    ProjAchievement, ProjAchievementReview, SysAttachment, SysUser,
)
from app.schemas.project import PROJECT_STATUS_FINISHED
from app.schemas.review import MIDTERM_STATUS_NAME
from app.utils.excel_helper import ExcelHelper

# 成果类型映射：与 proj_achievement.achievement_type 对应
ACHIEVEMENT_TYPE_NAME = {1: "论文", 2: "专利", 3: "软件著作权", 4: "竞赛获奖", 5: "创业成果", 6: "其他"}
# 成果级别映射：1=校级 2=省级 3=国家级
ACHIEVEMENT_LEVEL_NAME = {1: "校级", 2: "省级", 3: "国家级"}
# 成果认定状态映射：0=待认定 1=已认定 2=不通过
REVIEW_STATUS_NAME = {0: "待认定", 1: "已认定", 2: "不通过"}


def _fmt_date(v) -> str:
    """把日期/时间/字符串统一格式化为 YYYY-MM-DD，空值返回空串。"""
    if not v:
        return ""
    return str(v)[:10]


def _fmt_money(v) -> str:
    """把金额格式化为两位小数字符串；None/空值按 0 处理，避免 Excel 出现 None。"""
    return f"{Decimal(str(v or 0)):.2f}"


def _safe_name(name: str, default: str = "未命名") -> str:
    """去除文件/目录名中的非法字符。

    参数：name 原始名称；default 清洗后为空时的兜底名称。
    返回：最长 120 字符的安全名称。
    """
    name = re.sub(r'[\\/:*?"<>|\r\n]+', "_", (name or "").strip())
    return name[:120] or default


class ArchiveService:
    """结项归档导出服务：汇总业务数据，生成 Excel 并将附件一并打包为 ZIP。"""

    @staticmethod
    def export_zip(db: Session, project_id: int, operator: SysUser) -> Tuple[str, bytes]:
        """导出项目结项归档 ZIP。

        参数：
            db: 数据库会话。
            project_id: 项目 id。
            operator: 当前操作人，用于 ProjectService 的数据权限校验。
        返回：
            (建议下载文件名, ZIP 二进制内容)；文件在内存生成，不落临时文件。
        异常：
            项目不存在 / 非已结题状态 → ParamValidateException；
            无权限 → 由 ProjectService.get_detail 抛出。
        副作用：
            无数据库写入；仅读取项目、中期、成果、附件并生成内存 ZIP。
        注意：
            使用 ProjectService.get_detail 而不是直接查表，确保复用了项目级的
            负责人/学院/成员权限判断；附件源文件缺失不会中断导出。
        """
        # 延迟导入：避免 project_service 与本模块可能存在的循环依赖
        from app.services.project_service import ProjectService

        detail = ProjectService.get_detail(db, project_id, operator)
        # 归档是结题后的最终快照，未结题项目的材料仍可能变化，提前导出会产生不可信档案
        if detail.status != PROJECT_STATUS_FINISHED:
            raise ParamValidateException(message="仅已结题项目支持导出结项归档")
        project = ProjectCRUD.get_by_id(db, project_id)
        if not project:
            raise ParamValidateException(message="项目不存在")

        midterm = MidtermCRUD.get_by_project(db, project_id)
        achievements = db.query(ProjAchievement).filter(
            ProjAchievement.project_id == project_id,
            ProjAchievement.is_deleted == 0,
        ).order_by(ProjAchievement.id).all()
        ach_ids = [a.id for a in achievements]
        reviews: Dict[int, ProjAchievementReview] = {}
        if ach_ids:
            # 一次 IN 查询取全部成果认定记录，按成果 id 建索引，避免逐条查询
            for r in db.query(ProjAchievementReview).filter(
                ProjAchievementReview.achievement_id.in_(ach_ids),
                ProjAchievementReview.is_deleted == 0,
            ).all():
                reviews[r.achievement_id] = r

        # ---------- 1. 汇总 Excel ----------
        overview_rows = [
            {"k": "项目编号", "v": detail.project_no or "—"},
            {"k": "项目名称", "v": detail.project_name},
            {"k": "项目类型", "v": detail.project_type_name},
            {"k": "项目级别", "v": detail.project_level_name},
            {"k": "所属学院", "v": detail.college_name},
            {"k": "项目负责人", "v": detail.leader_name},
            {"k": "指导教师", "v": detail.teacher_name or "—"},
            {"k": "开始日期", "v": _fmt_date(detail.start_date)},
            {"k": "结束日期", "v": _fmt_date(detail.end_date)},
            {"k": "预算总额(元)", "v": _fmt_money(detail.budget_amount)},
            {"k": "已使用(元)", "v": _fmt_money(detail.used_amount)},
            {"k": "项目状态", "v": detail.status_name},
            {"k": "立项时间", "v": detail.approval_time.strftime("%Y-%m-%d %H:%M") if detail.approval_time else "—"},
            {"k": "归档时间", "v": datetime.now().strftime("%Y-%m-%d %H:%M")},
            {"k": "项目简介", "v": detail.project_summary or ""},
            {"k": "创新点", "v": detail.innovation_points or ""},
            {"k": "预期成果", "v": detail.expected_results or ""},
        ]
        team_rows = [{
            "name": m.student_name, "no": m.student_no, "major": m.major or "",
            "grade": m.grade or "", "role": m.role_in_team or "", "task": m.task_desc or "",
        } for m in detail.team_members]
        budget_rows = [{
            "item": b.budget_item,
            "amount": _fmt_money(b.budget_amount),
            "used": _fmt_money(b.used_amount),
            "remain": _fmt_money(Decimal(str(b.budget_amount or 0)) - Decimal(str(b.used_amount or 0))),
            "remark": b.remark or "",
        } for b in detail.budgets]
        midterm_rows = [{
            "k": "审核状态", "v": MIDTERM_STATUS_NAME.get(midterm.status, "") if midterm else "未提交",
        }, {
            "k": "当前进展", "v": midterm.progress_desc or "" if midterm else "",
        }, {
            "k": "已完成任务", "v": midterm.completed_tasks or "" if midterm else "",
        }, {
            "k": "剩余任务", "v": midterm.remaining_tasks or "" if midterm else "",
        }, {
            "k": "存在问题", "v": midterm.problems or "" if midterm else "",
        }, {
            "k": "下一步计划", "v": midterm.next_plan or "" if midterm else "",
        }, {
            "k": "已使用经费(元)", "v": _fmt_money(midterm.budget_usage) if midterm else "0.00",
        }, {
            "k": "审核意见", "v": midterm.review_comment or "" if midterm else "",
        }]
        ach_rows = [{
            "type": ACHIEVEMENT_TYPE_NAME.get(a.achievement_type, ""),
            "title": a.title,
            "author": a.author or "",
            "level": ACHIEVEMENT_LEVEL_NAME.get(a.level, ""),
            "award": a.award_level or "",
            "date": _fmt_date(a.publish_date),
            "no": a.achievement_no or "",
            "publisher": a.publisher or "",
            "review": REVIEW_STATUS_NAME.get(reviews[a.id].status if a.id in reviews else 1, ""),
            "review_comment": reviews[a.id].review_comment if a.id in reviews else "",
        } for a in achievements]
        final_rows = [{
            "k": "结项报告状态",
            "v": {0: "未提交", 1: "待验收", 2: "已通过", 3: "已驳回"}.get(detail.final_report_status, "—"),
        }, {
            "k": "验收专家数", "v": str(detail.final_review_total),
        }, {
            "k": "已提交意见专家数", "v": str(detail.final_review_done),
        }, {
            "k": "结项报告正文", "v": detail.final_report or "",
        }, {
            "k": "驳回意见", "v": detail.final_reject_reason or "",
        }]
        for item in detail.final_checklist:
            final_rows.append({
                "k": f"结项条件·{item.get('label', '')}",
                "v": f"{'通过' if item.get('passed') else '未通过'}（{item.get('detail', '')}）",
            })

        # ---------- 2. 附件收集 ----------
        # 统一收集为 (分类, 附件) 列表：分类决定 ZIP 内子目录，缺文件时用于清单标注
        attachments: List[Tuple[str, SysAttachment]] = []
        project_atts = db.query(SysAttachment).filter(
            SysAttachment.biz_type == "project",
            SysAttachment.biz_id == project_id,
            SysAttachment.is_deleted == 0,
        ).order_by(SysAttachment.id).all()
        for a in project_atts:
            attachments.append(("项目附件", a))
        if midterm:
            midterm_atts = db.query(SysAttachment).filter(
                SysAttachment.biz_type == "midterm",
                SysAttachment.biz_id == midterm.id,
                SysAttachment.is_deleted == 0,
            ).order_by(SysAttachment.id).all()
            for a in midterm_atts:
                attachments.append(("中期检查附件", a))
        if ach_ids:
            ach_atts = db.query(SysAttachment).filter(
                SysAttachment.biz_type == "achievement",
                SysAttachment.biz_id.in_(ach_ids),
                SysAttachment.is_deleted == 0,
            ).order_by(SysAttachment.id).all()
            ach_title = {a.id: a.title for a in achievements}
            for a in ach_atts:
                attachments.append((f"成果证明材料/{_safe_name(ach_title.get(a.biz_id, ''), str(a.biz_id))}", a))

        # ---------- 3. 打包 ----------
        buffer = io.BytesIO()
        att_rows: List[dict] = []
        packed_names: Dict[str, int] = {}
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for category, att in attachments:
                file_path = att.file_path or ""
                # 数据库存的是相对路径，按进程工作目录还原；绝对路径则原样使用
                if file_path and not os.path.isabs(file_path):
                    file_path = os.path.join(os.getcwd(), file_path)
                packed = bool(file_path and os.path.isfile(file_path))
                att_rows.append({
                    "category": category,
                    "name": att.file_name,
                    "size": _fmt_money(Decimal(att.file_size or 0) / Decimal(1024)) + " KB",
                    "packed": "是" if packed else "否（源文件缺失）",
                    "uploader": att.uploader_name or "",
                    "time": att.created_at.strftime("%Y-%m-%d %H:%M") if att.created_at else "",
                })
                if not packed:
                    continue
                folder = f"附件/{category}"
                base_name = _safe_name(att.file_name, f"附件_{att.id}")
                key = f"{folder}/{base_name}"
                # ZIP 内同名文件会互相覆盖，这里用出现次数追加 _2/_3 后缀去重
                if key in packed_names:
                    packed_names[key] += 1
                    stem, ext = os.path.splitext(base_name)
                    key = f"{folder}/{stem}_{packed_names[key]}{ext}"
                else:
                    packed_names[key] = 1
                zf.write(file_path, key)

            # 汇总 Excel 一次生成多 sheet 的字节流，直接写入 ZIP，避免落临时文件
            xlsx = ExcelHelper.export_sheets([
                ("项目概况", [("字段", "k"), ("内容", "v")], overview_rows),
                ("团队成员", [
                    ("姓名", "name"), ("学号", "no"), ("专业", "major"),
                    ("年级", "grade"), ("团队角色", "role"), ("分工", "task"),
                ], team_rows),
                ("预算执行", [
                    ("预算科目", "item"), ("预算(元)", "amount"), ("已用(元)", "used"),
                    ("结余(元)", "remain"), ("备注", "remark"),
                ], budget_rows),
                ("中期检查", [("字段", "k"), ("内容", "v")], midterm_rows),
                ("成果清单", [
                    ("类型", "type"), ("标题", "title"), ("作者", "author"),
                    ("级别", "level"), ("获奖等级", "award"), ("日期", "date"),
                    ("编号", "no"), ("发表/授权机构", "publisher"),
                    ("认定状态", "review"), ("认定意见", "review_comment"),
                ], ach_rows),
                ("结项验收", [("字段", "k"), ("内容", "v")], final_rows),
                ("附件清单", [
                    ("分类", "category"), ("文件名", "name"), ("大小", "size"),
                    ("是否打包", "packed"), ("上传人", "uploader"), ("上传时间", "time"),
                ], att_rows),
            ])
            zf.writestr("项目归档信息.xlsx", xlsx)

        zip_name = _safe_name(
            f"项目归档_{detail.project_no or detail.id}_{detail.project_name}"
        ) + ".zip"
        return zip_name, buffer.getvalue()
