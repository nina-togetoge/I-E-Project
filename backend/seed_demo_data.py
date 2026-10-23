"""
答辩演示数据生成脚本（重建库后使用）

生成内容：
  - 4 个项目（编号 01-04），负责人分别为 010101-010104，每个团队 4 人
  - 完整审核链路、中期检查、成果及认定、经费报销、结项验收记录
  - 每个项目的真实附件文件（申报书、实施方案/商业计划书、指导教师意见、
    中期报告、结项报告、成果证明、报销凭证），文件写入 static/uploads 并登记 sys_attachment

运行方式（在 backend 目录下）：
  python seed_demo_data.py
"""
import os
import uuid
import shutil
from pathlib import Path
from datetime import datetime, date, timedelta
from decimal import Decimal

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, Cm, RGBColor
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import text

from app.core.config import settings
from app.database.session import SessionLocal
from app.models import (
    ProjProject, ProjTeamMember, ProjBudget, ProjReview, ProjMidtermCheck,
    ProjAchievement, ProjAchievementReview, ProjExpense, SysAttachment, SysUser,
    Competition,
)
from app.services.certificate_service import CertificateService

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = Path(settings.UPLOAD_DIR)
if not UPLOAD_DIR.is_absolute():
    UPLOAD_DIR = BASE_DIR / UPLOAD_DIR

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PNG_MIME = "image/png"

FONT_PATH = "C:/Windows/Fonts/msyh.ttc"
FONT_BOLD_PATH = "C:/Windows/Fonts/msyhbd.ttc"


# ================================================================
# 文档生成工具
# ================================================================
def _init_doc():
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Cm(2.2)
    section.bottom_margin = Cm(2.2)
    section.left_margin = Cm(2.6)
    section.right_margin = Cm(2.4)
    normal = doc.styles["Normal"]
    normal.font.name = "宋体"
    normal.font.size = Pt(10.5)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    normal.paragraph_format.space_after = Pt(4)
    normal.paragraph_format.line_spacing = 1.35
    return doc


def _set_run_font(run, name="宋体", size=None, bold=None, color=None):
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if color:
        run.font.color.rgb = color


def _add_title(doc, text, subtitle=None):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    _set_run_font(run, "黑体", 18, True)
    if subtitle:
        p2 = doc.add_paragraph()
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r2 = p2.add_run(subtitle)
        _set_run_font(r2, "宋体", 10.5)
        r2.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
    doc.add_paragraph()


def _add_heading(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    run = p.add_run(text)
    _set_run_font(run, "黑体", 12, True)


def _add_para(doc, text, indent=True):
    p = doc.add_paragraph()
    if indent:
        p.paragraph_format.first_line_indent = Cm(0.74)
    run = p.add_run(text)
    _set_run_font(run, "宋体", 10.5)
    return p


def _add_bullets(doc, items):
    for item in items:
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Cm(0.74)
        p.paragraph_format.first_line_indent = Cm(-0.37)
        run = p.add_run(f"（{item[0]}）{item[1]}" if isinstance(item, tuple) else f"· {item}")
        _set_run_font(run, "宋体", 10.5)


def _add_table(doc, header, rows, widths=None):
    table = doc.add_table(rows=1, cols=len(header))
    table.style = "Table Grid"
    table.alignment = 1
    for i, text in enumerate(header):
        cell = table.rows[0].cells[i]
        cell.text = ""
        run = cell.paragraphs[0].add_run(text)
        _set_run_font(run, "宋体", 9, True)
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    for row in rows:
        cells = table.add_row().cells
        for i, value in enumerate(row):
            cells[i].text = ""
            run = cells[i].paragraphs[0].add_run(str(value))
            _set_run_font(run, "宋体", 9)
            cells[i].paragraphs[0].alignment = (
                WD_ALIGN_PARAGRAPH.CENTER if i == 0 or len(str(value)) <= 12 else WD_ALIGN_PARAGRAPH.LEFT
            )
    if widths:
        for i, width in enumerate(widths):
            for row in table.rows:
                row.cells[i].width = Cm(width)
    doc.add_paragraph()


def _add_signature(doc, role, name, day):
    doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = p.add_run(f"{role}（签字）：{name}")
    _set_run_font(run, "宋体", 10.5)
    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r2 = p2.add_run(day.strftime("%Y年%m月%d日"))
    _set_run_font(r2, "宋体", 10.5)


def _new_stored_path(ext):
    name = f"{datetime.now().strftime('%Y%m%d')}_{uuid.uuid4().hex}.{ext}"
    rel = f"static/uploads/{name}"
    return rel, UPLOAD_DIR / name


def _save_docx(doc, original_name):
    rel, abs_path = _new_stored_path("docx")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    doc.save(abs_path)
    return {
        "file_name": original_name, "file_path": rel, "abs_path": abs_path,
        "file_size": abs_path.stat().st_size, "file_type": DOCX_MIME, "file_ext": "docx",
    }


def _draw_wrapped(draw, text, font, max_width, start_y, fill, line_gap=14, center_x=None):
    """按像素宽度换行绘制文本，返回结束 y"""
    y = start_y
    line = ""
    for ch in text:
        test = line + ch
        if draw.textlength(test, font=font) > max_width:
            if center_x is not None:
                draw.text((center_x, y), line, font=font, fill=fill, anchor="ma")
            else:
                draw.text((60, y), line, font=font, fill=fill)
            y += font.size + line_gap
            line = ch
        else:
            line = test
    if line:
        if center_x is not None:
            draw.text((center_x, y), line, font=font, fill=fill, anchor="ma")
        else:
            draw.text((60, y), line, font=font, fill=fill)
        y += font.size + line_gap
    return y


def _save_png(image, original_name):
    rel, abs_path = _new_stored_path("png")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    image.save(abs_path, format="PNG")
    return {
        "file_name": original_name, "file_path": rel, "abs_path": abs_path,
        "file_size": abs_path.stat().st_size, "file_type": PNG_MIME, "file_ext": "png",
    }


def make_copyright_certificate(project, ach):
    """生成软件著作权登记证书图片"""
    img = Image.new("RGB", (1240, 860), "#fffdf7")
    draw = ImageDraw.Draw(img)
    title_font = ImageFont.truetype(FONT_BOLD_PATH, 44)
    body_font = ImageFont.truetype(FONT_PATH, 27)
    small_font = ImageFont.truetype(FONT_PATH, 23)
    red = (188, 32, 38)
    draw.rectangle([28, 28, 1212, 832], outline=red, width=6)
    draw.rectangle([44, 44, 1196, 816], outline=red, width=2)
    draw.text((620, 100), "计算机软件著作权登记证书", font=title_font, fill=red, anchor="ma")
    draw.line([(180, 172), (1060, 172)], fill=red, width=2)
    lines = [
        f"登记号：{ach['achievement_no']}",
        f"软件名称：{ach['title']}",
        f"著作权人：哈尔滨信息工程学院",
        f"开发完成日期：{ach['publish_date'].strftime('%Y年%m月%d日')}",
        f"首次发表日期：{ach['publish_date'].strftime('%Y年%m月%d日')}",
        "权利取得方式：原始取得",
        "权利范围：全部权利",
    ]
    y = 210
    for text in lines:
        draw.text((150, y), text, font=body_font, fill=(40, 40, 40))
        y += 52
    draw.text((150, y + 20), "根据《计算机软件保护条例》和《计算机软件著作权登记办法》的规定，", font=small_font, fill=(70, 70, 70))
    draw.text((150, y + 58), "经中国版权保护中心审核，对上述软件著作权予以登记。", font=small_font, fill=(70, 70, 70))
    # 印章
    draw.ellipse([880, 590, 1130, 840], outline=red, width=3)
    draw.text((1005, 670), "中国版权保护中心", font=small_font, fill=red, anchor="ma")
    draw.text((1005, 706), "登记专用章", font=small_font, fill=red, anchor="ma")
    draw.text((150, 750), f"登记日期：{ach['publish_date'].strftime('%Y年%m月%d日')}", font=small_font, fill=(70, 70, 70))
    return _save_png(img, f"{project['no']}-{project['name']}-软件著作权登记证书.png")


def make_award_certificate(project, ach):
    """生成竞赛获奖证书图片"""
    img = Image.new("RGB", (1240, 860), "#fffdf6")
    draw = ImageDraw.Draw(img)
    title_font = ImageFont.truetype(FONT_BOLD_PATH, 52)
    body_font = ImageFont.truetype(FONT_PATH, 28)
    small_font = ImageFont.truetype(FONT_PATH, 23)
    gold = (176, 126, 38)
    draw.rectangle([28, 28, 1212, 832], outline=gold, width=6)
    draw.rectangle([46, 46, 1194, 814], outline=gold, width=2)
    draw.text((620, 96), "获 奖 证 书", font=title_font, fill=(150, 20, 25), anchor="ma")
    draw.line([(240, 180), (1000, 180)], fill=gold, width=2)
    body = (
        f"{ach['author'].split('、')[0]} 同学：\n\n"
        f"    你（们）完成的《{project['name']}》在{ach['publisher']}主办的"
        f"{ach['publish_date'].strftime('%Y年')}校级大学生创新创业竞赛中，荣获{ach['award_level']}。\n"
        f"    特发此证，以资鼓励。"
    )
    y = 230
    for para in body.split("\n"):
        if not para.strip():
            y += 22
            continue
        y = _draw_wrapped(draw, para.strip(), body_font, 1060, y, (45, 45, 45), center_x=None)
    draw.ellipse([870, 570, 1120, 820], outline=(180, 30, 30), width=3)
    draw.text((995, 660), ach["publisher"], font=small_font, fill=(160, 25, 25), anchor="ma")
    draw.text((995, 696), "（盖章）", font=small_font, fill=(160, 25, 25), anchor="ma")
    draw.text((150, 750), ach["publish_date"].strftime("%Y年%m月%d日"), font=small_font, fill=(70, 70, 70))
    return _save_png(img, f"{project['no']}-{project['name']}-获奖证书.png")


def make_expense_receipt(project, expense):
    """生成经费报销凭证图片"""
    img = Image.new("RGB", (1240, 900), "white")
    draw = ImageDraw.Draw(img)
    title_font = ImageFont.truetype(FONT_BOLD_PATH, 38)
    body_font = ImageFont.truetype(FONT_PATH, 24)
    small_font = ImageFont.truetype(FONT_PATH, 21)
    black = (35, 35, 35)
    draw.text((620, 60), "经费报销凭证", font=title_font, fill=black, anchor="ma")
    draw.text((620, 120), "哈尔滨信息工程学院 · 创新创业项目", font=small_font, fill=(90, 90, 90), anchor="ma")
    draw.line([(80, 165), (1160, 165)], fill=(120, 120, 120), width=2)
    rows = [
        ("报销单号", expense["expense_no"]),
        ("项目编号", project["no"]),
        ("项目名称", project["name"]),
        ("报销人", expense["applicant_name"]),
        ("费用说明", expense["expense_desc"]),
        ("发票号码", expense["invoice_no"]),
        ("报销金额", f"¥ {expense['expense_amount']:,} 元"),
        ("审批状态", "已完成（指导教师、学院、财务三级审批）"),
        ("报销日期", expense["approval_time"].strftime("%Y年%m月%d日")),
    ]
    y = 200
    for label, value in rows:
        draw.text((110, y), f"{label}：", font=body_font, fill=black)
        if label == "费用说明":
            y = _draw_wrapped(draw, value, body_font, 760, y, black, line_gap=8)
            y = max(y, y + 10)
        else:
            draw.text((290, y), str(value), font=body_font, fill=black)
            y += 62
    draw.line([(80, 800), (1160, 800)], fill=(120, 120, 120), width=1)
    draw.text((110, 820), "经办人：财务处  王敏", font=small_font, fill=(80, 80, 80))
    draw.text((860, 820), "审核：李国强", font=small_font, fill=(80, 80, 80))
    return _save_png(img, f"{project['no']}-{project['name']}-经费报销凭证.png")


# ================================================================
# 各类文档内容
# ================================================================
def build_application_doc(project):
    doc = _init_doc()
    _add_title(doc, "大学生创新创业训练计划项目申报书", f"项目编号：{project['no']}")
    _add_heading(doc, "一、项目基本情况")
    _add_table(
        doc,
        ["项目", "内容", "项目", "内容"],
        [
            ["项目名称", project["name"], "项目类别", project["type_name"]],
            ["所属学院", "计算机科学与技术学院", "项目级别", project["level_name"]],
            ["负 责 人", project["leader_name"], "指导教师", "陶静华"],
            ["参赛赛事", project["competition_name"], "起止时间", project["period_text"]],
            ["预算总额", f"¥ {project['budget']:,}", "团队人数", "4 人"],
        ],
        widths=[2.6, 6.2, 2.6, 4.2],
    )
    _add_heading(doc, "二、项目简介")
    _add_para(doc, project["summary"])
    _add_heading(doc, "三、立项背景与意义")
    for text in project["background"]:
        _add_para(doc, text)
    _add_heading(doc, "四、研究内容与技术路线")
    _add_bullets(doc, project["content_points"])
    _add_heading(doc, "五、创新点")
    _add_bullets(doc, project["innovation_points"])
    _add_heading(doc, "六、预期成果")
    _add_para(doc, project["expected"])
    _add_heading(doc, "七、进度安排")
    _add_table(doc, ["阶段", "时间", "主要任务"], project["schedule"], widths=[2.4, 4.2, 9.0])
    _add_heading(doc, "八、经费预算")
    _add_table(
        doc, ["序号", "预算科目", "金额（元）", "测算依据"],
        [[i + 1, item["name"], f"{item['amount']:,}", item["remark"]] for i, item in enumerate(project["budget_items"])]
        + [["合计", "", f"{project['budget']:,}", ""]],
        widths=[1.6, 4.2, 3.2, 7.0],
    )
    _add_heading(doc, "九、团队成员及分工")
    _add_table(
        doc, ["序号", "学号", "姓名", "专业", "团队角色", "主要分工"],
        [[i + 1, m["student_no"], m["student_name"], m["major"], m["role"], m["task"]]
         for i, m in enumerate(project["members"])],
        widths=[1.4, 2.6, 2.2, 4.0, 2.8, 5.2],
    )
    _add_para(doc, "本人承诺：所填写的申报材料真实、准确，项目研究内容不侵犯他人知识产权，"
                   "严格按照学校和赛事要求开展研究并按期提交中期检查与结项材料。")
    _add_signature(doc, "项目负责人", project["leader_name"], project["submit_date"])
    return _save_docx(doc, f"{project['no']}-{project['name']}-项目申报书.docx")


def build_plan_doc(project):
    """实施方案 / 商业计划书"""
    doc = _init_doc()
    if project["is_business"]:
        _add_title(doc, "商业计划书", project["name"])
        _add_heading(doc, "一、项目概述")
        _add_para(doc, project["summary"])
        _add_heading(doc, "二、市场分析")
        for text in project["market"]:
            _add_para(doc, text)
        _add_heading(doc, "三、产品与服务方案")
        _add_bullets(doc, project["content_points"])
        _add_heading(doc, "四、商业模式")
        for text in project["business_model"]:
            _add_para(doc, text)
        _add_heading(doc, "五、竞争分析")
        for text in project["competition_analysis"]:
            _add_para(doc, text)
        _add_heading(doc, "六、运营与推广计划")
        _add_bullets(doc, project["promotion"])
        _add_heading(doc, "七、财务预测")
        _add_table(
            doc, ["项目", "第一年", "第二年", "说明"],
            project["financial_rows"], widths=[4.4, 3.2, 3.2, 6.0],
        )
        _add_heading(doc, "八、风险与应对")
        _add_bullets(doc, project["risks"])
        return _save_docx(doc, f"{project['no']}-{project['name']}-商业计划书.docx")

    _add_title(doc, "项目实施方案", project["name"])
    _add_heading(doc, "一、总体目标")
    _add_para(doc, project["summary"])
    _add_heading(doc, "二、技术路线")
    _add_bullets(doc, project["tech_route"])
    _add_heading(doc, "三、功能与模块划分")
    _add_bullets(doc, project["content_points"])
    _add_heading(doc, "四、开发环境")
    _add_table(doc, ["类别", "选型", "说明"], project["tech_stack"], widths=[4.0, 5.0, 7.5])
    _add_heading(doc, "五、进度计划")
    _add_table(doc, ["阶段", "时间", "交付物"], project["milestones"], widths=[3.0, 4.4, 9.0])
    _add_heading(doc, "六、风险与应对")
    _add_bullets(doc, project["risks"])
    return _save_docx(doc, f"{project['no']}-{project['name']}-项目实施方案.docx")


def build_teacher_recommendation(project):
    doc = _init_doc()
    _add_title(doc, "指导教师推荐意见")
    _add_para(doc, f"项目名称：{project['name']}")
    _add_para(doc, f"项目负责人：{project['leader_name']}（{project['leader_no']}）")
    _add_para(doc, f"项目类别：{project['type_name']}　项目级别：{project['level_name']}")
    _add_heading(doc, "推荐意见")
    _add_para(doc, project["teacher_comment"])
    _add_para(doc, "经审阅项目申报材料，该项目选题符合专业培养方向，研究内容与团队能力匹配，"
                   "进度安排和经费预算合理，具备实施条件。本人同意担任指导教师并推荐该项目申报。")
    _add_para(doc, "承诺将按照学校大学生创新创业训练计划管理办法要求，定期指导学生开展研究，"
                   "审核中期检查与结项材料，确保项目按期保质完成。")
    _add_signature(doc, "指导教师", "陶静华", project["submit_date"])
    return _save_docx(doc, f"{project['no']}-{project['name']}-指导教师推荐意见.docx")


def build_midterm_doc(project):
    doc = _init_doc()
    mid = project["midterm"]
    _add_title(doc, "大学生创新创业训练计划项目中期检查报告", f"项目编号：{project['no']}")
    _add_heading(doc, "一、项目基本情况")
    _add_table(
        doc, ["项目名称", project["name"], "负责人", project["leader_name"]],
        [["指导教师", "陶静华", "立项时间", project["approval_date"].strftime("%Y年%m月")]],
        widths=[3.0, 8.0, 3.0, 3.4],
    )
    _add_heading(doc, "二、当前进展")
    _add_para(doc, mid["progress"])
    _add_heading(doc, "三、已完成任务")
    _add_bullets(doc, mid["completed"])
    _add_heading(doc, "四、存在问题")
    _add_para(doc, mid["problems"])
    _add_heading(doc, "五、下一步计划")
    _add_bullets(doc, mid["next"])
    _add_heading(doc, "六、经费使用情况")
    _add_table(
        doc, ["预算总额", "已使用", "执行率", "说明"],
        [[f"¥ {project['budget']:,}", f"¥ {project['used']:,}",
          f"{project['used'] / project['budget'] * 100:.1f}%", "主要用于设备材料采购、测试与资料费"]],
        widths=[3.6, 3.6, 2.4, 7.4],
    )
    _add_para(doc, "项目组承诺以上情况真实，后续将按计划推进剩余任务，按期提交结项材料。")
    _add_signature(doc, "项目负责人", project["leader_name"],
                   mid["submit_date"] or project["submit_date"])
    return _save_docx(doc, f"{project['no']}-{project['name']}-中期检查报告.docx")


def build_final_doc(project):
    doc = _init_doc()
    _add_title(doc, "大学生创新创业训练计划项目结项验收报告", f"项目编号：{project['no']}")
    _add_heading(doc, "一、项目完成情况")
    _add_para(doc, project["final"]["completion"])
    _add_heading(doc, "二、主要研究成果")
    _add_bullets(doc, project["final"]["results"])
    _add_heading(doc, "三、成果应用与推广")
    _add_para(doc, project["final"]["application"])
    _add_heading(doc, "四、经费决算")
    _add_table(
        doc, ["预算科目", "预算金额（元）", "实际支出（元）", "结余（元）"],
        [[item["name"], f"{item['amount']:,}", f"{item['used']:,}", f"{item['amount'] - item['used']:,}"]
         for item in project["budget_items"]]
        + [["合计", f"{project['budget']:,}", f"{project['used']:,}", f"{project['budget'] - project['used']:,}"]],
        widths=[5.0, 4.0, 4.2, 3.4],
    )
    _add_heading(doc, "五、总结与展望")
    _add_para(doc, project["final"]["summary"])
    _add_para(doc, "项目组认为，本项目已完成申报书确定的全部研究任务和成果指标，"
                   "经费使用规范，同意提交结项验收，请专家组审核。")
    _add_signature(doc, "项目负责人", project["leader_name"], project["final"]["submit_date"])
    return _save_docx(doc, f"{project['no']}-{project['name']}-结项验收报告.docx")


def build_paper_notice(project, ach):
    doc = _init_doc()
    _add_title(doc, "论文录用通知")
    _add_para(doc, f"{ach['author'].split('、')[0]} 同志：")
    _add_para(doc, f"您（们）撰写的论文《{ach['title']}》经本刊编辑部初审、同行专家外审及编委会终审，"
                   f"已被《{ach['publisher']}》录用，拟定于 {ach['publish_date'].strftime('%Y年第%m期')} 刊发。")
    _add_table(
        doc, ["论文题目", ach["title"]],
        [
            ["作者", ach["author"]],
            ["作者单位", "哈尔滨信息工程学院"],
            ["期刊名称", ach["publisher"]],
            ["录用日期", ach["publish_date"].strftime("%Y年%m月%d日")],
            ["DOI", ach["achievement_no"]],
        ],
        widths=[3.4, 12.0],
    )
    _add_para(doc, "请按编辑部要求完成排版校对，并在见刊后及时将论文首页及检索页上传至项目管理系统，"
                   "作为项目成果认定材料。")
    _add_signature(doc, "编辑部", ach["publisher"], ach["publish_date"])
    return _save_docx(doc, f"{project['no']}-{project['name']}-论文录用通知.docx")


# ================================================================
# 演示项目定义
# ================================================================
PROJECTS = [
    {
        "no": "01",
        "name": "基于Vue+FastAPI的校园创新创业项目管理平台",
        "type": 1, "type_name": "创新训练项目", "level": 2, "level_name": "校级",
        "status": 0,
        "competition_name": "第十三届中国国际大学生创新大赛",
        "competition_id": 42,
        "leader_no": "010101", "leader_name": "朱艳怡",
        "teacher_no": "01001", "teacher_name": "陶静华",
        "period_text": "2026-10 至 2027-09",
        "start_date": date(2026, 10, 15), "end_date": date(2027, 9, 30),
        "budget": 8000, "used": 0,
        "summary": "面向高校创新创业项目管理场景，采用 Vue 3 与 FastAPI 构建前后端分离的一体化平台，"
                   "覆盖项目申报、三级审核、中期检查、成果登记、经费报销与结项归档全流程，"
                   "解决现有管理中流程分散、数据重复填报、审核进度不透明的问题。",
        "background": [
            "目前学校创新创业项目依托多个 Excel 台账和线下签字流转，申报材料格式不统一，"
            "学院初审、校级复审、专家评审之间缺少状态衔接，学生难以及时了解项目所处环节。",
            "随着项目数量逐年增加，成果、经费、中期检查和结项材料分散存放，统计与归档工作量大。"
            "建设一套覆盖全生命周期的管理平台，有助于提升管理效率和数据质量。",
        ],
        "content_points": [
            "项目申报：支持草稿保存、团队成员维护、预算明细填写和附件上传。",
            "分级审核：指导教师确认、学院初审、校级复审、专家评审按状态机自动流转。",
            "过程管理：中期检查、变更申请、成果登记与认定、经费报销按阶段开放。",
            "结项归档：自动校验中期结果、成果数量和报销状态，支持归档材料导出。",
        ],
        "innovation_points": [
            "以状态机驱动项目全生命周期流转，审核节点与项目状态严格绑定，避免越级审批。",
            "统一阶段页交互，将分散的功能入口整合为申报、审核、过程、结项四类工作台。",
            "按角色、学院、项目归属三级控制数据权限，专家评审采用盲审脱敏展示。",
        ],
        "expected": "形成可运行的项目管理平台一套、软件著作权 1 项、使用说明书 1 份，"
                    "并在计算机科学与技术学院完成不少于 50 个项目的试点应用。",
        "schedule": [
            ["需求与设计", "2026.10-2026.12", "完成需求调研、流程梳理、数据库与接口设计"],
            ["核心开发", "2027.01-2027.05", "完成申报、审核、过程管理、结项归档模块"],
            ["测试试点", "2027.06-2027.08", "完成功能测试、权限测试并在学院试点"],
            ["总结验收", "2027.09", "整理文档、申请软著、提交结项材料"],
        ],
        "budget_items": [
            {"name": "设备费", "amount": 3000, "used": 0, "remark": "开发用服务器与测试终端"},
            {"name": "材料费", "amount": 1500, "used": 0, "remark": "打印耗材、移动存储等"},
            {"name": "测试化验加工费", "amount": 1000, "used": 0, "remark": "第三方兼容性测试"},
            {"name": "差旅费", "amount": 1000, "used": 0, "remark": "兄弟院校调研"},
            {"name": "出版/文献/信息传播费", "amount": 1500, "used": 0, "remark": "软著登记与资料费"},
        ],
        "members": [
            {"name": "韩芳鹏", "role": "后端开发", "task": "接口设计与权限控制"},
            {"name": "云军涵", "role": "前端开发", "task": "阶段页与组件开发"},
            {"name": "孙娜", "role": "测试与文档", "task": "测试用例、使用手册与数据整理"},
        ],
        "tech_route": [
            "前端采用 Vue 3 + TypeScript + Element Plus，按角色动态生成路由与菜单。",
            "后端采用 FastAPI + SQLAlchemy，按领域拆分项目、审核、用户、统计服务。",
            "数据库采用 MySQL 8，通过状态字段与审核记录表保证流程可追溯。",
        ],
        "tech_stack": [
            ["前端", "Vue 3 / TypeScript / Element Plus", "组件化开发，统一阶段页交互"],
            ["后端", "FastAPI / SQLAlchemy", "RESTful 接口与业务服务分层"],
            ["数据库", "MySQL 8", "事务保证审核与状态流转一致性"],
            ["部署", "Nginx / Uvicorn", "前后端分离部署"],
        ],
        "milestones": [
            ["需求与设计", "2026.10-2026.12", "需求规格说明书、原型、数据库设计"],
            ["核心开发", "2027.01-2027.05", "可运行的申报与审核模块"],
            ["测试试点", "2027.06-2027.08", "测试报告、试点总结"],
            ["总结验收", "2027.09", "软著证书、结项报告"],
        ],
        "risks": [
            "需求变更风险：采用迭代开发，每个阶段与指导教师确认范围。",
            "进度风险：核心模块并行开发，设置双周检查节点。",
            "数据安全风险：按角色最小授权，敏感操作记录日志。",
        ],
        "teacher_comment": "该项目针对学校创新创业项目管理中的实际痛点，选题具有明确的应用价值。"
                           "负责人具备较好的前后端开发基础，团队成员分工清晰，技术路线可行，进度安排合理，"
                           "同意推荐申报。",
        "is_business": False,
        "market": [], "business_model": [], "competition_analysis": [], "promotion": [],
        "financial_rows": [],
        "submit_date": date(2026, 6, 20),
        "approval_date": None,
        "submit_time": None,
        "approval_time": None,
        "midterm": None,
        "achievements": [],
        "expense": None,
        "final": None,
        "reviews": [],
    },
    {
        "no": "02",
        "name": "面向校园的智能垃圾分类回收系统",
        "type": 2, "type_name": "创业训练项目", "level": 2, "level_name": "校级",
        "status": 6,
        "competition_name": "第十三届中国国际大学生创新大赛",
        "competition_id": 42,
        "leader_no": "010102", "leader_name": "施艳",
        "teacher_no": "01001", "teacher_name": "陶静华",
        "period_text": "2026-07 至 2027-06",
        "start_date": date(2026, 7, 1), "end_date": date(2027, 6, 30),
        "budget": 12000, "used": 3500,
        "summary": "面向校园场景的智能垃圾分类回收系统，通过图像识别与称重传感结合，实现投放引导、"
                   "满溢监测、积分激励和清运调度，提升校园可回收物分拣效率，降低后勤清运成本。",
        "background": [
            "校园生活垃圾中可回收物占比接近三成，但分类投放准确率不高，现有回收点缺少投放引导和"
            "满溢预警，清运依赖人工巡查，容易出现溢桶和混投。",
            "项目拟以低成本边缘识别终端改造现有回收点，结合后台调度与积分激励，"
            "在不更换原有桶体的前提下提升分类效果，具有较好的推广条件。",
        ],
        "content_points": [
            "智能回收终端：摄像头识别投放物类别，称重后自动计重并给出投放提示。",
            "满溢监测：超声波传感器采集桶内高度，超过阈值自动上报。",
            "积分激励：按可回收物重量折算积分，可在校园一卡通或小程序兑换。",
            "清运调度：后台按满溢程度和路线生成清运任务，记录清运轨迹。",
        ],
        "innovation_points": [
            "轻量化识别模型部署在边缘端，断网情况下仍可完成分类引导。",
            "满溢监测与清运路线联动，减少无效巡查和溢桶投诉。",
            "积分激励与校园一卡通打通，提高学生持续参与率。",
        ],
        "expected": "完成智能回收样机 2 台、管理后台 1 套、软件著作权 1 项，"
                    "在 2 栋宿舍楼开展为期 8 周的试运行，分类准确率达到 90% 以上。",
        "schedule": [
            ["需求与选型", "2026.07-2026.08", "完成场景调研、硬件选型与原型设计"],
            ["样机开发", "2026.09-2026.12", "完成识别终端、称重与满溢监测模块"],
            ["系统联调", "2027.01-2027.03", "完成后台、积分与调度功能联调"],
            ["试运行", "2027.04-2027.05", "宿舍楼试运行与数据评估"],
            ["总结验收", "2027.06", "整理成果、申请软著、提交结项"],
        ],
        "budget_items": [
            {"name": "设备费", "amount": 5000, "used": 2000, "remark": "摄像头、称重与超声传感器"},
            {"name": "材料费", "amount": 3000, "used": 800, "remark": "终端外壳、线材与安装辅材"},
            {"name": "测试化验加工费", "amount": 1500, "used": 400, "remark": "样机加工与老化测试"},
            {"name": "差旅费", "amount": 1500, "used": 200, "remark": "回收企业调研"},
            {"name": "出版/文献/信息传播费", "amount": 1000, "used": 100, "remark": "软著登记与资料费"},
        ],
        "members": [
            {"name": "陈涛刚", "role": "硬件开发", "task": "终端结构与传感器集成"},
            {"name": "赵超", "role": "算法开发", "task": "垃圾图像识别模型训练与部署"},
            {"name": "云伟", "role": "后端与运营", "task": "调度后台开发与试运行组织"},
        ],
        "market": [
            "黑龙江省高校在校生规模稳定，校园生活垃圾中可回收物占比较高，后勤部门对低成本分类改造"
            "存在持续需求。初步调研显示，受访高校后勤部门中超过七成愿意试点智能回收终端。",
            "同类产品多为整桶替换方案，单点投入高。本项目以加装式终端切入，改造成本约为整桶方案的"
            "三分之一，更适合在既有回收点批量部署。",
        ],
        "business_model": [
            "设备销售与租赁：向高校后勤或物业公司提供终端设备，按点位收取设备款或年度租赁费。",
            "运营服务：提供清运调度、数据报表和积分运营服务，按服务点位收取年度服务费。",
            "再生资源分成：与回收企业合作，按可回收物实际回收量获取一定比例分成。",
        ],
        "competition_analysis": [
            "整桶智能回收设备厂商：功能完整但价格高，适合新建校区，存量改造场景优势不明显。",
            "普通分类垃圾桶：成本低但无识别与满溢监测，无法解决混投和溢桶问题。",
            "本项目定位于存量点位低成本改造，以加装终端和调度服务形成差异化。",
        ],
        "promotion": [
            "以本校 2 栋宿舍楼为样板点，形成可量化的分类准确率和清运成本对比数据。",
            "联合后勤与学生会开展积分兑换活动，提高初期参与率。",
            "通过高校后勤协会会议和区域高校走访推广样板案例。",
        ],
        "financial_rows": [
            ["营业收入", "18.0 万元", "45.0 万元", "设备销售、租赁与服务费"],
            ["营业成本", "11.5 万元", "27.0 万元", "终端制造、安装与运维"],
            ["期间费用", "4.0 万元", "8.0 万元", "市场推广与人员"],
            ["净利润", "2.5 万元", "10.0 万元", "含再生资源分成"],
        ],
        "risks": [
            "识别准确率受光照和投放姿态影响：通过多场景样本训练和补光设计降低影响。",
            "设备损坏与人为破坏：采用防拆结构与保险方案，明确点位管理责任。",
            "推广周期较长：先以校内样板点验证，再逐步扩展到周边高校。",
        ],
        "tech_route": [],
        "tech_stack": [],
        "milestones": [],
        "teacher_comment": "该项目选题紧扣校园环保需求，团队在嵌入式开发和算法部署方面已有前期积累，"
                           "样机方案成本可控，商业模式清晰，同意推荐申报。",
        "is_business": True,
        "submit_date": date(2026, 6, 25),
        "approval_date": date(2026, 7, 8),
        "submit_time": datetime(2026, 6, 25, 15, 20),
        "approval_time": datetime(2026, 7, 8, 16, 30),
        "midterm": {
            "status": 0,
            "progress": "已完成需求调研、硬件选型和第一版样机结构设计，识别模型在自建数据集上"
                        "准确率达到 92.3%，称重与满溢监测模块完成单点调试，后台原型正在开发。",
            "completed": [
                "完成 2 栋宿舍楼回收点位的实地测量与投放行为观察。",
                "完成摄像头、称重传感器和超声波传感器的选型与采购。",
                "完成垃圾图像数据集采集与标注，共 6800 张。",
                "完成第一版终端结构件加工与装配。",
            ],
            "problems": "夜间光照不足时识别准确率下降约 6 个百分点；终端外壳防水等级尚未完成测试。",
            "next": [
                "补充夜间样本并优化补光方案。",
                "完成终端防水与老化测试。",
                "开发清运调度与积分后台功能。",
                "在 1 栋宿舍楼开展小范围试运行。",
            ],
            "budget_usage": 3500,
            "submit_date": None,
            "review_time": None,
            "reviewer_id": None,
            "review_comment": None,
        },
        "achievements": [
            {
                "type": 3, "title": "校园智能垃圾分类回收系统 V1.0",
                "author": "施艳、陈涛刚、赵超",
                "publish_date": date(2026, 9, 15),
                "publisher": "中华人民共和国国家版权局",
                "achievement_no": "2026SR0987654", "level": 1, "award_level": None,
                "summary": "系统实现投放识别、称重计分、满溢监测和清运调度功能，"
                           "已在 1 栋宿舍楼完成内部测试部署。",
                "certificate": "copyright",
            },
        ],
        "expense": {
            "expense_no": "BX2026-0701",
            "applicant_name": "施艳",
            "expense_amount": 3500,
            "expense_desc": "垃圾分类识别终端摄像头、称重传感器采购及样机结构件加工",
            "invoice_no": "02345678",
            "approval_time": datetime(2026, 8, 28, 10, 0),
            "budget_item_name": "设备费",
        },
        "final": None,
        "reviews": [
            {"stage": 0, "reviewer": "teacher", "result": 1,
             "comment": "项目选题结合校园环保需求，技术路线清晰，同意提交学院审核。",
             "time": datetime(2026, 6, 26, 10, 0)},
            {"stage": 1, "reviewer": "college", "result": 1,
             "comment": "申报材料完整，经费预算合理，符合学院推荐条件，同意通过初审。",
             "time": datetime(2026, 6, 29, 14, 30)},
            {"stage": 2, "reviewer": "university", "result": 1,
             "comment": "项目方案可行，预期成果明确，同意通过校级复审并进入专家评审。",
             "time": datetime(2026, 7, 3, 9, 30)},
            {"stage": 3, "reviewer": "expert1", "result": 1, "score": Decimal("91.00"),
             "dims": {"创新性": 92, "可行性": 90, "团队": 89, "应用价值": 93},
             "comment": "项目聚焦校园垃圾分类场景，识别方案成熟，建议补充分类准确率的长期运行数据，同意立项。",
             "time": datetime(2026, 7, 8, 15, 0)},
            {"stage": 3, "reviewer": "expert2", "result": 1, "score": Decimal("87.50"),
             "dims": {"创新性": 86, "可行性": 88, "团队": 86, "应用价值": 90},
             "comment": "系统架构清晰，硬件选型合理，终端部署成本偏高，建议优化后推广，同意立项。",
             "time": datetime(2026, 7, 8, 16, 10)},
        ],
    },
    {
        "no": "03",
        "name": "基于知识图谱的课程学习推荐平台",
        "type": 1, "type_name": "创新训练项目", "level": 2, "level_name": "校级",
        "status": 8,
        "competition_name": "第十三届中国国际大学生创新大赛",
        "competition_id": 42,
        "leader_no": "010103", "leader_name": "范娟辉",
        "teacher_no": "01001", "teacher_name": "陶静华",
        "period_text": "2026-07 至 2027-06",
        "start_date": date(2026, 7, 1), "end_date": date(2027, 6, 30),
        "budget": 15000, "used": 4200,
        "summary": "构建覆盖课程、知识点、先修关系与学习资源的知识图谱，结合协同过滤与图神经网络"
                   "实现个性化学习资源推荐，并在《数据结构》课程中开展应用验证。",
        "background": [
            "学生在课程学习中面临资源分散、难度匹配不准的问题，现有推荐多基于点击行为，"
            "缺少对知识点先后依赖的建模，容易出现推荐内容与当前学习阶段不匹配。",
            "课程大纲、教材目录和历年试题中包含较丰富的知识结构信息，通过知识图谱组织这些关系，"
            "可以为个性化推荐提供可解释的依据。",
        ],
        "content_points": [
            "知识图谱构建：抽取课程、章节、知识点、先修关系和资源实体，形成领域图谱。",
            "学习诊断：根据作业与测验结果定位薄弱知识点，生成学习路径。",
            "资源推荐：融合协同过滤与图神经网络，输出个性化资源列表并给出推荐理由。",
            "效果评估：在《数据结构》课程开展对照实验，比较学习效果与满意度。",
        ],
        "innovation_points": [
            "融合课程大纲与教材构建领域知识图谱，实体和关系经过教师人工校验。",
            "图神经网络与协同过滤混合推荐，缓解冷启动问题。",
            "推荐结果附带知识路径解释，提升可解释性和教师可控性。",
        ],
        "expected": "建成包含 1.2 万个节点、4.5 万条关系的课程知识图谱；发表论文 1 篇；"
                    "登记软件著作权 1 项；在 2 个教学班完成应用验证。",
        "schedule": [
            ["图谱构建", "2026.07-2026.10", "完成课程知识体系梳理与图谱初版"],
            ["算法开发", "2026.11-2027.02", "完成诊断与混合推荐算法"],
            ["平台开发", "2027.03-2027.05", "完成推荐平台与教师端"],
            ["应用验证", "2027.06", "教学班对照实验与总结"],
        ],
        "budget_items": [
            {"name": "设备费", "amount": 6000, "used": 1800, "remark": "图数据库服务器租赁"},
            {"name": "材料费", "amount": 2000, "used": 400, "remark": "数据标注与资料整理"},
            {"name": "测试化验加工费", "amount": 2000, "used": 500, "remark": "算法评测与标注外包"},
            {"name": "差旅费", "amount": 2000, "used": 300, "remark": "教学研讨会"},
            {"name": "出版/文献/信息传播费", "amount": 3000, "used": 1200, "remark": "论文版面费与软著登记"},
        ],
        "members": [
            {"name": "潘杰平", "role": "图谱构建", "task": "知识点抽取、关系校验与图谱存储"},
            {"name": "施文", "role": "算法开发", "task": "学习诊断与混合推荐模型"},
            {"name": "戚永", "role": "平台开发", "task": "推荐平台前后端与实验数据采集"},
        ],
        "tech_route": [
            "使用 Neo4j 存储课程知识图谱，节点覆盖课程、章节、知识点与资源。",
            "采用 BERT 抽取知识点，结合教师校验保证实体与关系质量。",
            "推荐层使用 LightGCN 与协同过滤加权融合，输出 Top-N 资源。",
            "通过平台埋点采集学习行为，开展对照实验评估效果。",
        ],
        "tech_stack": [
            ["图数据库", "Neo4j 5", "存储知识图谱与先修关系"],
            ["算法框架", "PyTorch / PyTorch Geometric", "图神经网络推荐模型"],
            ["后端", "FastAPI", "推荐服务与学习行为接口"],
            ["前端", "Vue 3 / ECharts", "学习路径与推荐结果展示"],
        ],
        "milestones": [
            ["图谱构建", "2026.07-2026.10", "课程知识图谱初版与校验报告"],
            ["算法开发", "2026.11-2027.02", "推荐算法与离线评测结果"],
            ["平台开发", "2027.03-2027.05", "推荐平台可用版本"],
            ["应用验证", "2027.06", "对照实验报告与结项材料"],
        ],
        "risks": [
            "图谱质量风险：引入教师人工校验环节，按章节分批验收。",
            "数据不足风险：先使用公开课程数据集预训练，再逐步积累校本数据。",
            "应用推广风险：选择 2 个教学班试点，控制实验范围。",
        ],
        "teacher_comment": "该项目将知识图谱技术应用于课程学习推荐，选题与专业方向契合度高，"
                           "团队具备图数据库和推荐算法基础，前期已完成课程知识体系梳理，同意推荐申报。",
        "is_business": False,
        "market": [], "business_model": [], "competition_analysis": [], "promotion": [],
        "financial_rows": [],
        "submit_date": date(2026, 6, 12),
        "approval_date": date(2026, 6, 30),
        "submit_time": datetime(2026, 6, 12, 11, 0),
        "approval_time": datetime(2026, 6, 30, 15, 20),
        "midterm": {
            "status": 2,
            "progress": "已完成《数据结构》《计算机网络》两门课程的知识图谱构建，共 1.2 万个节点、"
                        "4.5 万条关系；推荐算法完成离线评测，NDCG@10 较基线提升 11.6%；平台主体功能已上线。",
            "completed": [
                "完成课程大纲、教材与题库的知识点抽取和教师校验。",
                "完成知识图谱入库与可视化查询。",
                "完成 LightGCN 与协同过滤混合推荐模型。",
                "完成学习诊断、推荐列表和教师端资源管理功能。",
            ],
            "problems": "冷启动用户推荐效果波动较大；平台与教务系统数据同步接口尚未联调。",
            "next": [
                "引入学习目标与先修关系约束，改善冷启动推荐。",
                "完成教务数据同步接口联调。",
                "在 2 个教学班开展对照实验。",
                "整理论文与软著材料。",
            ],
            "budget_usage": 4200,
            "submit_date": datetime(2026, 9, 18, 10, 0),
            "review_time": datetime(2026, 9, 22, 14, 30),
            "reviewer_id": "teacher",
            "review_comment": "项目按计划完成知识图谱构建与推荐算法开发，阶段成果达到中期考核要求，同意通过中期检查。",
        },
        "achievements": [
            {
                "type": 3, "title": "课程知识图谱构建与推荐系统 V1.0",
                "author": "范娟辉、施文、戚永",
                "publish_date": date(2026, 8, 20),
                "publisher": "中华人民共和国国家版权局",
                "achievement_no": "2026SR1023456", "level": 1, "award_level": None,
                "summary": "系统实现课程知识图谱构建、学习诊断、个性化资源推荐与教师端管理功能。",
                "certificate": "copyright",
            },
            {
                "type": 1, "title": "基于知识图谱的个性化学习资源推荐方法",
                "author": "范娟辉、施文、陶静华",
                "publish_date": date(2026, 9, 1),
                "publisher": "软件导刊",
                "achievement_no": "10.19788/j.issn.1004-731X.2026.07.012",
                "level": 1, "award_level": None,
                "summary": "提出融合知识路径约束与图神经网络的推荐方法，在自建课程数据集上"
                           "NDCG@10 较基线提升 11.6%。",
                "certificate": "paper",
            },
        ],
        "expense": {
            "expense_no": "BX2026-0702",
            "applicant_name": "范娟辉",
            "expense_amount": 4200,
            "expense_desc": "图数据库服务器租赁、数据标注服务及论文版面费",
            "invoice_no": "02349876",
            "approval_time": datetime(2026, 9, 2, 9, 30),
            "budget_item_name": "设备费",
        },
        "final": None,
        "reviews": [
            {"stage": 0, "reviewer": "teacher", "result": 1,
             "comment": "项目围绕知识图谱技术开展学习资源推荐研究，专业契合度高，同意提交学院审核。",
             "time": datetime(2026, 6, 14, 9, 0)},
            {"stage": 1, "reviewer": "college", "result": 1,
             "comment": "团队配置合理，前期调研充分，同意通过学院初审。",
             "time": datetime(2026, 6, 20, 10, 30)},
            {"stage": 2, "reviewer": "university", "result": 1,
             "comment": "研究内容充实，技术路线可行，同意通过校级复审。",
             "time": datetime(2026, 6, 24, 15, 0)},
            {"stage": 3, "reviewer": "expert1", "result": 1, "score": Decimal("93.00"),
             "dims": {"创新性": 95, "可行性": 91, "团队": 92, "应用价值": 94},
             "comment": "知识图谱构建方法完整，推荐算法离线指标良好，创新性突出，建议优先支持。",
             "time": datetime(2026, 6, 28, 14, 0)},
            {"stage": 3, "reviewer": "expert2", "result": 1, "score": Decimal("89.00"),
             "dims": {"创新性": 88, "可行性": 90, "团队": 88, "应用价值": 90},
             "comment": "选题具有应用价值，建议补充冷启动场景的实验验证，同意立项。",
             "time": datetime(2026, 6, 28, 15, 20)},
        ],
    },
    {
        "no": "04",
        "name": "校园二手交易小程序的设计与实现",
        "type": 3, "type_name": "创业实践项目", "level": 2, "level_name": "校级",
        "status": 9,
        "competition_name": "2026年校级大学生创新创业大赛",
        "competition_id": 54,
        "leader_no": "010104", "leader_name": "施芳平",
        "teacher_no": "01001", "teacher_name": "陶静华",
        "period_text": "2026-05 至 2026-10",
        "start_date": date(2026, 5, 15), "end_date": date(2026, 10, 15),
        "budget": 20000, "used": 5000,
        "summary": "面向校园的二手交易小程序，提供实名认证、商品发布、站内沟通、担保交易与信用评价功能，"
                   "降低校内闲置物品流转成本，提升交易安全性。",
        "background": [
            "校园闲置物品交易主要依赖微信群和论坛，信息分散、缺少信用约束，交易纠纷难以追溯。"
            "学生群体交易频次高、单笔金额小，适合以轻量小程序承载。",
            "学校已有统一身份认证体系，可为实名和信用机制提供基础，项目具备落地条件。",
        ],
        "content_points": [
            "实名认证：对接学校统一身份认证，区分在校生与校友身份。",
            "商品发布：支持图片、成色、价格、交易方式和自提点选择。",
            "站内沟通：提供文字与图片沟通，敏感信息过滤。",
            "担保交易：买家付款至平台托管，确认收货后结算给卖家。",
            "信用评价：交易完成后双向评价，累计信用分并展示。",
        ],
        "innovation_points": [
            "校园实名体系与信用分结合，降低虚假信息和恶意交易。",
            "担保交易与校内自提点联动，兼顾资金安全与交付效率。",
            "基于浏览与成交行为的商品推荐，提高闲置物品匹配效率。",
        ],
        "expected": "小程序上线并覆盖 3 个学院，累计注册用户 1200 人、成交 600 单；"
                    "发表论文 1 篇；获校级大学生创新创业竞赛奖项 1 项。",
        "schedule": [
            ["需求与设计", "2026.05-2026.06", "完成需求调研、原型与接口设计"],
            ["开发与测试", "2026.07-2026.08", "完成小程序、后台与担保交易功能"],
            ["试运行", "2026.09", "覆盖 3 个学院开展试运行"],
            ["总结验收", "2026.10", "整理成果、提交结项材料"],
        ],
        "budget_items": [
            {"name": "设备费", "amount": 8000, "used": 2000, "remark": "云服务器与测试机"},
            {"name": "材料费", "amount": 3000, "used": 600, "remark": "小程序认证与短信服务"},
            {"name": "测试化验加工费", "amount": 3000, "used": 800, "remark": "安全测试与压力测试"},
            {"name": "差旅费", "amount": 3000, "used": 800, "remark": "竞赛答辩与调研"},
            {"name": "出版/文献/信息传播费", "amount": 3000, "used": 800, "remark": "论文版面费与资料"},
        ],
        "members": [
            {"name": "韩建", "role": "后端开发", "task": "交易、担保与信用评价接口"},
            {"name": "潘杰平", "role": "前端开发", "task": "小程序页面与交互"},
            {"name": "严国军", "role": "运营与测试", "task": "试运行推广、测试与数据统计"},
        ],
        "market": [
            "校内二手交易需求稳定，毕业季和开学季为交易高峰。现有微信群交易流程依赖人工确认，"
            "缺少担保和信用记录，纠纷处理成本高。",
            "目标用户为在校本科生与研究生，首期覆盖 3 个学院，后续可扩展到全校并承接校园服务类交易。",
        ],
        "business_model": [
            "交易服务费：担保交易按成交金额收取低比例服务费，试运行期免收。",
            "自提点合作：与校内快递点、便利店合作设置自提点，按单量结算。",
            "增值服务：为校内商家提供合规的商品推广位。",
        ],
        "competition_analysis": [
            "通用二手平台：品类全但校园场景渗透不足，缺少校内实名与自提网络。",
            "校园微信群：信息发布快但无担保和信用机制，纠纷多。",
            "本项目以校内实名、担保交易和自提点形成差异化，先做深校园场景。",
        ],
        "promotion": [
            "在 3 个学院开展开学季推广，结合学生会活动设置线下宣传点。",
            "首单担保交易免服务费，邀请同学注册可获得信用加分。",
            "与校内快递点合作设置自提点，提升交付便利性。",
        ],
        "financial_rows": [
            ["营业收入", "6.0 万元", "15.0 万元", "服务费、推广位与自提点分成"],
            ["营业成本", "3.8 万元", "8.5 万元", "服务器、短信与运营"],
            ["期间费用", "1.5 万元", "3.0 万元", "推广与人员"],
            ["净利润", "0.7 万元", "3.5 万元", "试运行期以投入为主"],
        ],
        "risks": [
            "交易纠纷风险：引入担保交易、信用评价与申诉处理机制。",
            "用户增长不及预期：以学院为单位分阶段推广，设置推广激励机制。",
            "合规风险：禁止违禁品交易，建立关键词审核与人工复核。",
        ],
        "tech_route": [],
        "tech_stack": [],
        "milestones": [],
        "teacher_comment": "该项目面向校园真实交易场景，已完成需求调研和原型设计，团队具备小程序开发与运营经验，"
                           "商业模式清晰，风险应对措施可行，同意推荐申报。",
        "is_business": True,
        "submit_date": date(2026, 4, 20),
        "approval_date": date(2026, 5, 10),
        "submit_time": datetime(2026, 4, 20, 10, 0),
        "approval_time": datetime(2026, 5, 10, 14, 0),
        "midterm": {
            "status": 2,
            "progress": "小程序已完成实名认证、商品发布、站内沟通和担保交易功能，8 月底上线试运行，"
                        "覆盖 3 个学院，累计注册用户 860 人、成交 310 单，信用评价与申诉流程运行正常。",
            "completed": [
                "完成需求调研与原型设计，确定交易与信用规则。",
                "完成小程序端与后台管理端开发。",
                "完成担保交易支付与结算流程联调。",
                "在 3 个学院开展试运行并建立 2 个自提点。",
            ],
            "problems": "高峰期商品审核存在延迟；部分用户对担保交易流程不熟悉，需要加强引导。",
            "next": [
                "优化商品审核队列，增加敏感词与图片复核。",
                "完善新手引导和交易流程提示。",
                "扩大试点学院范围并统计成交数据。",
                "整理论文与竞赛申报材料。",
            ],
            "budget_usage": 5000,
            "submit_date": datetime(2026, 7, 20, 9, 30),
            "review_time": datetime(2026, 7, 25, 15, 0),
            "reviewer_id": "teacher",
            "review_comment": "小程序已上线试运行，用户规模与功能完成度符合中期目标，经费使用合理，同意通过中期检查。",
        },
        "achievements": [
            {
                "type": 1, "title": "校园二手交易平台的设计与实现",
                "author": "施芳平、韩建、陶静华",
                "publish_date": date(2026, 6, 15),
                "publisher": "计算机教育",
                "achievement_no": "10.19788/j.issn.1004-731X.2026.09.021",
                # 成果级别与项目级别映射不同（成果 1校级/2省级/3国家级），此处按校级填写
                "level": 1, "award_level": None,
                "summary": "论文总结校园二手交易平台的实名认证、担保交易与信用评价设计，"
                           "并给出试运行数据分析。",
                "certificate": "paper",
            },
            {
                "type": 4, "title": "2026年校级大学生创新创业大赛",
                "author": "施芳平、韩建、潘杰平、严国军",
                "publish_date": date(2026, 8, 20),
                "publisher": "创新创业学院",
                "achievement_no": "XJ2026-0312", "level": 1, "award_level": "二等奖",
                "summary": "项目获2026年校级大学生创新创业大赛创业实践组二等奖。",
                "certificate": "award",
            },
        ],
        "expense": {
            "expense_no": "BX2026-0703",
            "applicant_name": "施芳平",
            "expense_amount": 5000,
            "expense_desc": "云服务器与短信服务费、小程序认证费、竞赛答辩差旅费",
            "invoice_no": "02351234",
            "approval_time": datetime(2026, 9, 12, 11, 0),
            "budget_item_name": "设备费",
        },
        "final": {
            "completion": "项目按计划完成校园二手交易小程序的开发与试运行，实现实名认证、商品发布、"
                          "站内沟通、担保交易、信用评价和后台管理等功能。试运行覆盖 3 个学院，"
                          "累计注册用户 1200 人、成交 600 单，达到申报书确定的指标。",
            "results": [
                "校园二手交易小程序 1 套（学生端、管理后台）。",
                "发表论文《校园二手交易平台的设计与实现》1 篇。",
                "获2026年校级大学生创新创业大赛二等奖 1 项。",
                "形成交易规则、信用评价与申诉处理制度各 1 份。",
            ],
            "application": "小程序已在 3 个学院稳定运行，建立 2 个校内自提点，"
                           "后续计划扩展至全校并接入更多校园生活服务场景。",
            "summary": "项目完成了从需求调研、系统设计、开发测试到试运行的全过程，"
                       "验证了实名认证与担保交易在校园二手交易场景中的可行性。"
                       "团队成员在工程实践、项目管理和成果表达方面得到系统锻炼。",
            "submit_date": date(2026, 10, 10),
            "report_text": "本项目围绕校园二手交易中的信息分散、信用缺失和交付不安全问题，"
                           "设计并实现了基于微信小程序的校园二手交易平台。平台以学校统一身份认证为基础，"
                           "构建实名认证、商品发布、站内沟通、担保交易、信用评价和申诉处理六大模块。"
                           "试运行期间覆盖 3 个学院，注册用户 1200 人，累计成交 600 单，"
                           "交易纠纷率控制在 1.2% 以内。项目完成申报书确定的全部研究任务，"
                           "形成论文 1 篇、校级竞赛奖项 1 项，经费使用规范，申请结项验收。",
        },
        "reviews": [
            {"stage": 0, "reviewer": "teacher", "result": 1,
             "comment": "项目面向校园二手交易场景，需求明确，同意提交学院审核。",
             "time": datetime(2026, 4, 22, 10, 0)},
            {"stage": 1, "reviewer": "college", "result": 1,
             "comment": "选题具有实用价值，预算编制规范，同意通过学院初审。",
             "time": datetime(2026, 4, 28, 14, 20)},
            {"stage": 2, "reviewer": "university", "result": 1,
             "comment": "项目已具备实施基础，同意通过校级复审。",
             "time": datetime(2026, 5, 6, 9, 40)},
            {"stage": 3, "reviewer": "expert1", "result": 1, "score": Decimal("92.00"),
             "dims": {"创新性": 91, "可行性": 93, "团队": 90, "应用价值": 94},
             "comment": "项目贴近校园实际需求，已形成可运行产品，技术路线清晰，同意立项。",
             "time": datetime(2026, 5, 8, 15, 0)},
            {"stage": 3, "reviewer": "expert2", "result": 1, "score": Decimal("90.00"),
             "dims": {"创新性": 89, "可行性": 91, "团队": 89, "应用价值": 91},
             "comment": "小程序功能完整、迭代节奏合理，建议加强交易安全与信用约束机制，同意立项。",
             "time": datetime(2026, 5, 8, 16, 20)},
            {"stage": 4, "reviewer": "expert1", "result": 1,
             "comment": "结项材料齐全，系统运行稳定，已完成预期成果指标，同意结题。",
             "time": datetime(2026, 10, 14, 10, 0)},
            {"stage": 4, "reviewer": "expert2", "result": 1,
             "comment": "项目按计划完成全部任务，经费使用规范，成果证明材料完整，同意结题。",
             "time": datetime(2026, 10, 14, 15, 30)},
        ],
    },
]


# ================================================================
# 主流程
# ================================================================
PROJECT_TABLES = [
    "proj_certificate", "proj_achievement_review", "proj_achievement", "proj_expense", "proj_budget",
    "proj_review", "proj_midterm_check", "proj_change_request",
    "proj_team_member", "proj_project",
]


def clear_tables(db):
    db.execute(text("SET FOREIGN_KEY_CHECKS=0"))
    for table in PROJECT_TABLES + ["sys_attachment"]:
        db.execute(text(f"TRUNCATE TABLE `{table}`"))
    db.execute(text("SET FOREIGN_KEY_CHECKS=1"))
    # 证书相关的站内通知会随成果重建而失效，一并清理
    db.execute(text("DELETE FROM sys_notification WHERE biz_type = 'certificate'"))
    db.commit()
    if UPLOAD_DIR.exists():
        for item in UPLOAD_DIR.iterdir():
            if item.is_file():
                item.unlink()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def get_user(db, username):
    user = db.query(SysUser).filter(SysUser.username == username).first()
    if not user:
        raise RuntimeError(f"账号 {username} 不存在")
    return user


def get_competition(db, title, fallback_id):
    """按名称取大赛，避免重建库后自增 ID 变化导致挂错赛事"""
    comp = db.query(Competition).filter(Competition.title == title).first()
    if comp is None:
        comp = db.get(Competition, fallback_id)
    if comp is None:
        raise RuntimeError(f"大赛 {title} 不存在")
    return comp


def add_attachment(db, meta, biz_type, biz_id, uploader, created_at):
    row = SysAttachment(
        biz_type=biz_type,
        biz_id=biz_id,
        file_name=meta["file_name"],
        file_path=meta["file_path"],
        file_size=meta["file_size"],
        file_type=meta["file_type"],
        file_ext=meta["file_ext"],
        uploader_id=uploader.id,
        uploader_name=uploader.real_name,
        download_count=0,
        created_at=created_at,
        updated_at=created_at,
        is_deleted=0,
    )
    db.add(row)
    return row


def seed(db):
    clear_tables(db)

    for cfg in PROJECTS:
        leader = get_user(db, cfg["leader_no"])
        teacher = get_user(db, cfg["teacher_no"])
        expert1 = get_user(db, "0101")
        expert2 = get_user(db, "0201")
        college_admin = get_user(db, "11111")
        super_admin = get_user(db, "00000")
        comp = get_competition(db, cfg["competition_name"], cfg["competition_id"])

        project = ProjProject(
            project_no=cfg["no"],
            project_name=cfg["name"],
            project_type=cfg["type"],
            project_level=cfg["level"],
            college_id=leader.college_id,
            leader_id=leader.id,
            teacher_id=teacher.id,
            competition_id=comp.id,
            competition_session="2026届",
            start_date=cfg["start_date"],
            end_date=cfg["end_date"],
            budget_amount=Decimal(cfg["budget"]),
            used_amount=Decimal(cfg["used"]),
            project_summary=cfg["summary"],
            innovation_points="\n".join(
                f"{i + 1}. {text}" for i, text in enumerate(cfg["innovation_points"])
            ) if isinstance(cfg["innovation_points"], list) else cfg["innovation_points"],
            expected_results=cfg["expected"],
            status=cfg["status"],
            submit_time=cfg["submit_time"],
            approval_time=cfg["approval_time"],
            current_approver_id=None,
            reject_reason=None,
            created_at=cfg["submit_time"] or datetime(2026, 6, 18, 9, 0),
            updated_at=cfg["approval_time"] or cfg["submit_time"] or datetime(2026, 10, 20, 9, 0),
            is_deleted=0,
        )
        db.add(project)
        db.flush()
        pid = project.id
        cfg["_pid"] = pid

        # 预算
        budget_rows = {}
        for item in cfg["budget_items"]:
            row = ProjBudget(
                project_id=pid,
                budget_item=item["name"],
                budget_amount=Decimal(item["amount"]),
                used_amount=Decimal(item["used"]),
                remark=item["remark"],
            )
            db.add(row)
            db.flush()
            budget_rows[item["name"]] = row.id

        # 团队成员
        for m in cfg["members"]:
            user = get_user_by_name(db, m["name"])
            db.add(ProjTeamMember(
                project_id=pid,
                student_id=user.id,
                student_name=user.real_name,
                student_no=user.username,
                major=user.major or "计算机科学与技术",
                grade="2023级",
                role_in_team=m["role"],
                task_desc=m["task"],
                join_time=cfg["submit_time"] or datetime(2026, 6, 18, 9, 0),
            ))

        # 审核记录
        reviewer_map = {
            "teacher": teacher, "college": college_admin,
            "university": super_admin, "expert1": expert1, "expert2": expert2,
        }
        for rv in cfg["reviews"]:
            reviewer = reviewer_map[rv["reviewer"]]
            db.add(ProjReview(
                project_id=pid,
                review_stage=rv["stage"],
                reviewer_id=reviewer.id,
                reviewer_name=reviewer.real_name,
                review_result=rv["result"],
                score=rv.get("score"),
                dim_scores=rv.get("dims"),
                review_comment=rv["comment"],
                review_time=rv["time"],
                created_at=rv["time"],
                updated_at=rv["time"],
                is_deleted=0,
            ))
        db.flush()

        # 中期检查
        midterm_cfg = cfg["midterm"]
        if midterm_cfg:
            reviewer = teacher if midterm_cfg.get("reviewer_id") == "teacher" else None
            midterm = ProjMidtermCheck(
                project_id=pid,
                progress_desc=midterm_cfg["progress"],
                completed_tasks="；".join(midterm_cfg["completed"]),
                remaining_tasks="；".join(midterm_cfg["next"]),
                problems=midterm_cfg["problems"],
                next_plan="；".join(midterm_cfg["next"]),
                report=None,
                budget_usage=Decimal(midterm_cfg["budget_usage"]),
                status=midterm_cfg["status"],
                reviewer_id=reviewer.id if reviewer else None,
                review_comment=midterm_cfg["review_comment"],
                review_time=midterm_cfg["review_time"],
                submit_time=midterm_cfg["submit_date"],
                created_at=midterm_cfg["submit_date"] or datetime(2026, 9, 10, 9, 0),
                updated_at=midterm_cfg["review_time"] or datetime(2026, 9, 10, 9, 0),
                is_deleted=0,
            )
            db.add(midterm)
            db.flush()
            cfg["_midterm_id"] = midterm.id

        # 成果及认定
        cfg["_achievements"] = []
        for ach_cfg in cfg["achievements"]:
            ach = ProjAchievement(
                project_id=pid,
                achievement_type=ach_cfg["type"],
                title=ach_cfg["title"],
                author=ach_cfg["author"],
                publish_date=ach_cfg["publish_date"],
                publisher=ach_cfg["publisher"],
                achievement_no=ach_cfg["achievement_no"],
                level=ach_cfg["level"],
                award_level=ach_cfg["award_level"],
                summary=ach_cfg["summary"],
                created_at=datetime.combine(ach_cfg["publish_date"], datetime.min.time()) + timedelta(days=1),
                updated_at=datetime.combine(ach_cfg["publish_date"], datetime.min.time()) + timedelta(days=2),
                is_deleted=0,
            )
            db.add(ach)
            db.flush()
            review = ProjAchievementReview(
                achievement_id=ach.id,
                status=1,
                reviewer_id=teacher.id,
                reviewer_name=teacher.real_name,
                review_comment="材料真实有效，与项目研究内容一致，予以认定。",
                review_time=datetime.combine(ach_cfg["publish_date"], datetime.min.time()) + timedelta(days=3),
                submit_time=datetime.combine(ach_cfg["publish_date"], datetime.min.time()) + timedelta(days=1),
            )
            db.add(review)
            cfg["_achievements"].append((ach, ach_cfg))

        # 报销
        expense_cfg = cfg["expense"]
        if expense_cfg:
            expense = ProjExpense(
                expense_no=expense_cfg["expense_no"],
                project_id=pid,
                applicant_id=leader.id,
                applicant_name=expense_cfg["applicant_name"],
                expense_amount=Decimal(expense_cfg["expense_amount"]),
                budget_item_id=budget_rows.get(expense_cfg["budget_item_name"]),
                expense_desc=expense_cfg["expense_desc"],
                invoice_no=expense_cfg["invoice_no"],
                status=6,
                submit_time=expense_cfg["approval_time"] - timedelta(days=8),
                approval_time=expense_cfg["approval_time"],
                created_at=expense_cfg["approval_time"] - timedelta(days=8),
                updated_at=expense_cfg["approval_time"],
                is_deleted=0,
            )
            db.add(expense)
            db.flush()
            cfg["_expense"] = (expense, expense_cfg)

        # 结项报告占位记录
        if cfg["final"]:
            final = cfg["final"]
            report_time = datetime.combine(final["submit_date"], datetime.min.time()) + timedelta(hours=10)
            report = ProjReview(
                project_id=pid,
                review_stage=4,
                reviewer_id=leader.id,
                reviewer_name=leader.real_name,
                review_result=99,
                review_comment="[结项报告] " + final["report_text"],
                review_time=report_time,
                created_at=report_time,
                updated_at=report_time,
                is_deleted=0,
            )
            db.add(report)
            db.flush()
            cfg["_final_report"] = report

        db.flush()
        generate_attachments(db, cfg, leader, teacher)
        # 校级竞赛获奖：平台自动生成团队证书 + 每位成员个人证书（与后台"生成获奖名单"一致）
        for ach, ach_cfg in cfg["_achievements"]:
            if ach_cfg.get("type") != 4:
                continue
            if comp.level != 1:
                continue
            CertificateService.issue_for_achievement(db, ach, project, comp, ach.award_level, super_admin)
        db.commit()
        print(f"[项目{cfg['no']}] 已生成：{cfg['name']}（负责人 {cfg['leader_no']} {cfg['leader_name']}）")

    print("演示数据生成完成")


def get_user_by_name(db, real_name):
    user = db.query(SysUser).filter(
        SysUser.real_name == real_name, SysUser.role == 1
    ).order_by(SysUser.id).first()
    if not user:
        raise RuntimeError(f"学生 {real_name} 不存在")
    return user


def generate_attachments(db, cfg, leader, teacher):
    """生成真实附件文件并登记"""
    project = {
        "no": cfg["no"], "name": cfg["name"], "type_name": cfg["type_name"],
        "level_name": cfg["level_name"], "leader_name": leader.real_name,
        "leader_no": leader.username, "competition_name": cfg["competition_name"],
        "period_text": cfg["period_text"], "budget": cfg["budget"], "used": cfg["used"],
        "summary": cfg["summary"], "background": cfg["background"],
        "content_points": cfg["content_points"], "innovation_points": cfg["innovation_points"],
        "expected": cfg["expected"], "schedule": cfg["schedule"],
        "budget_items": cfg["budget_items"], "members": cfg["members"],
        "teacher_comment": cfg["teacher_comment"], "submit_date": cfg["submit_date"],
        "approval_date": cfg["approval_date"] or cfg["submit_date"],
        "is_business": cfg["is_business"],
        "market": cfg["market"], "business_model": cfg["business_model"],
        "competition_analysis": cfg["competition_analysis"], "promotion": cfg["promotion"],
        "financial_rows": cfg["financial_rows"], "risks": cfg["risks"],
        "tech_route": cfg["tech_route"], "tech_stack": cfg["tech_stack"],
        "milestones": cfg["milestones"],
        "midterm": cfg["midterm"], "final": cfg["final"],
    }
    # 成员信息补充学号/专业
    members = []
    for m in cfg["members"]:
        user = get_user_by_name(db, m["name"])
        members.append({
            "student_name": user.real_name, "student_no": user.username,
            "major": user.major or "计算机科学与技术", "role": m["role"], "task": m["task"],
        })
    project["members"] = members

    pid = cfg["_pid"]
    created = cfg["submit_time"] or datetime(2026, 6, 18, 9, 0)
    metas = []

    meta = build_application_doc(project)
    metas.append((meta, "project", pid, leader, created))

    meta = build_plan_doc(project)
    metas.append((meta, "project", pid, leader, created + timedelta(hours=1)))

    meta = build_teacher_recommendation(project)
    metas.append((meta, "project", pid, teacher, created + timedelta(hours=5)))

    if cfg["midterm"] and cfg["_midterm_id"]:
        meta = build_midterm_doc(project)
        metas.append((meta, "midterm", cfg["_midterm_id"], leader,
                      cfg["midterm"]["submit_date"] or datetime(2026, 9, 12, 10, 0)))

    if cfg["final"]:
        meta = build_final_doc(project)
        metas.append((meta, "project", pid, leader,
                      datetime.combine(cfg["final"]["submit_date"], datetime.min.time()) + timedelta(hours=9)))

    for ach, ach_cfg in cfg["_achievements"]:
        if ach_cfg["certificate"] == "copyright":
            meta = make_copyright_certificate(project, ach_cfg)
        elif ach_cfg["certificate"] == "award":
            meta = make_award_certificate(project, ach_cfg)
        else:
            meta = build_paper_notice(project, ach_cfg)
        metas.append((meta, "achievement", ach.id, leader,
                      datetime.combine(ach_cfg["publish_date"], datetime.min.time()) + timedelta(days=2)))

    if cfg["expense"]:
        expense, expense_cfg = cfg["_expense"]
        meta = make_expense_receipt(project, expense_cfg)
        metas.append((meta, "expense", expense.id, leader, expense_cfg["approval_time"] - timedelta(days=1)))

    for meta, biz_type, biz_id, uploader, ts in metas:
        add_attachment(db, meta, biz_type, biz_id, uploader, ts)


def main():
    db = SessionLocal()
    try:
        seed(db)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
