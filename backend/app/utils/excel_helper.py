"""
Excel 导入导出工具类（基于 openpyxl）
实现功能：
1. 批量用户/项目数据导入
2. 项目名单/经费台账/评审结果/操作日志导出
3. 导入模板下载
4. 导入错误校验（逐行校验 + 错误信息汇总）

调用方：
    app/services/user_service.py、project_service.py、archive_service.py 等
    负责导入导出的服务；路由层只负责把字节流包成 StreamingResponse。

关键设计：
    - 列定义（ColumnDef）同时驱动「生成模板」「解析上传文件」「逐格校验」三件事，
      保证模板与解析规则不会各写一套而漂移；
    - 导入采用「整表校验、错误汇总」策略：不是遇到第一个错误就中断，
      而是一次性把所有行的问题返回给用户，减少反复上传；
    - 导出统一使用内存 BytesIO，不落临时文件，避免并发导出时的磁盘清理问题；
    - 金额一律用 Decimal 计算并以字符串写入，禁止 float 参与金额运算，
      防止 0.1+0.2 之类的二进制误差进入经费台账；
    - 不使用合并单元格：导入时每行必须能被独立解析，合并会让 data_start_row
      之后的行出现空值，且列宽/表头也无需靠合并表达层级。
"""
import os
import io
import re
from typing import List, Dict, Any, Tuple, Optional, Type, Callable
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    Workbook = None  # type: ignore


from app.core.config import settings
from app.core.exceptions import ParamValidateException


# ====================================================================
# 列定义：用于生成模板/读取/校验
# ====================================================================
class ColumnDef:
    """单列表格定义。

    一行 ColumnDef 同时描述：表头文案、写入数据库的字段名、单元格类型、
    是否必填、最大长度、枚举映射（显示值 -> 实际值）、正则格式与默认值。
    生成模板、解析上传文件、逐格校验都读取这份定义，因此新增导入字段时
    只需在这里加一行，模板与校验会自动保持一致。

    :param header: 表头文案，带 * 表示必填，仅用于展示；解析时会把 * 去掉再比对
    :param field: 目标字典/模型字段名
    :param col_type: 期望的 Python 类型（str/int/float/Decimal/date/datetime/bool）
    :param required: 必填；为空时报错而不是使用默认值
    :param max_length: 字符串最大长度，超长直接报错，避免写库时被截断
    :param choices: 枚举映射，Excel 里写中文显示值，落库时转成数字/实际值
    :param pattern: 正则校验（如手机号、账号），只对字符串生效
    :param default: 选填列为空时写入的值
    :param desc: 模板第 2 行注释里的填写说明
    """

    def __init__(
        self, header: str, field: str, col_type: Type = str,
        required: bool = False, max_length: Optional[int] = None,
        choices: Optional[Dict[Any, Any]] = None,  # 显示值 -> 实际值 映射
        pattern: Optional[str] = None,             # 正则校验
        default: Any = None,
        desc: str = "",
    ):
        self.header = header
        self.field = field
        self.col_type = col_type
        self.required = required
        self.max_length = max_length
        self.choices = choices
        self.pattern = re.compile(pattern) if pattern else None
        self.default = default
        self.desc = desc

    def validate(self, raw_value: Any) -> Tuple[Any, Optional[str]]:
        """
        校验单元格原始值，返回 (转换后值, 错误信息或None)

        校验顺序：必填 -> 枚举 -> 类型转换 -> 长度 -> 正则。
        先做枚举再做类型转换，是因为枚举列在 Excel 中是中文文本，
        必须先映射成数字，后面的 int 转换才不会失败。

        :param raw_value: openpyxl 读出的原始值（可能是 str/int/float/datetime/None）
        :return: 成功时 (转换后的值, None)；失败时 (None, 中文错误信息)
        :side effect: 无，纯函数，不修改 ColumnDef 自身
        """
        # 1. 必填校验
        # 空字符串按「空」处理：用户在单元格里敲空格也会被 strip 后判空。
        if raw_value is None or (isinstance(raw_value, str) and raw_value.strip() == ""):
            if self.required:
                return None, f"必填项为空"
            return self.default, None

        # 字符串预处理
        # 去掉首尾空白，避免「 学生 」这种脏数据导致枚举匹配失败。
        value = raw_value
        if isinstance(value, str):
            value = value.strip()

        # 2. 枚举选择
        # 只接受模板里列出的显示值，拒绝「学生(1)」这类模糊写法，
        # 保证落库的枚举值可控；错误信息回显全部合法选项，方便用户改正。
        if self.choices:
            if value not in self.choices:
                return None, f"值 '{value}' 不在允许选项中: {list(self.choices.keys())}"
            value = self.choices[value]

        # 3. 类型转换
        # 各类型的容错策略不同，逐个说明见下方分支；
        # 任何转换失败都统一返回中文提示，不把 Python 异常抛给用户。
        try:
            if self.col_type == bool:
                # 布尔兼容「true/1/是/y/yes」，因为 Excel 里可能被填成任意一种。
                if isinstance(value, bool):
                    pass
                elif isinstance(value, (int, float)):
                    value = bool(value)
                else:
                    value = str(value).lower() in ("true", "1", "是", "y", "yes")
            elif self.col_type == int:
                # Excel 数字列会被读成 float（如 1.0），先转 int 再校验；
                # 1.5 这类非整数也会被 int() 静默截断，属于宽松处理，
                # 因为导入模板中的整数列（角色、学院编码）不应出现小数。
                if isinstance(value, float) and value.is_integer():
                    value = int(value)
                else:
                    value = int(value)
            elif self.col_type == float:
                value = float(value)
            elif self.col_type == Decimal:
                # 金额先转字符串再转 Decimal，避免 float 的二进制误差。
                value = Decimal(str(value))
            elif self.col_type == date:
                # Excel 日期单元格会被 openpyxl 直接读成 datetime，取 .date() 即可；
                # 文本单元格则依次尝试 3 种常见分隔符，全部失败才算格式错误。
                if isinstance(value, datetime):
                    value = value.date()
                elif isinstance(value, date):
                    pass
                else:
                    # 常见格式尝试
                    text = str(value)
                    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
                        try:
                            value = datetime.strptime(text, fmt).date()
                            break
                        except ValueError:
                            continue
                    else:
                        return None, f"日期格式无效，支持 YYYY-MM-DD"
            elif self.col_type == datetime:
                # 时间列允许省略秒（Excel 中常被格式化为到分钟），
                # 也允许只填日期，按当天 00:00:00 处理。
                if isinstance(value, datetime):
                    pass
                else:
                    text = str(value)
                    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                        try:
                            value = datetime.strptime(text, fmt)
                            break
                        except ValueError:
                            continue
                    else:
                        return None, f"时间格式无效"
            elif self.col_type == str:
                value = str(value)
        except (ValueError, InvalidOperation):
            # Decimal 的非法输入抛 InvalidOperation，数值转换抛 ValueError，统一收口。
            return None, f"类型转换失败，期望 {self.col_type.__name__}"

        # 4. 长度校验
        # 在写库前截断风险最高的环节拦截，避免 MySQL 严格模式下整批导入失败。
        if self.max_length and isinstance(value, str) and len(value) > self.max_length:
            return None, f"长度超过最大限制 {self.max_length}"

        # 5. 正则校验
        # 用 match 而非 fullmatch；现有 pattern 均带 ^...$，等价于整串匹配。
        if self.pattern and isinstance(value, str) and not self.pattern.match(value):
            return None, f"格式不匹配规则"

        return value, None


# ====================================================================
# 模板定义：用户导入 / 项目导入
# 列表顺序即 Excel 列顺序，解析时按位置一一对应，调整顺序需同步通知前端；
# 表头文案中的 * 仅代表必填，入库前会去掉再与上传文件比对。
# ====================================================================
USER_IMPORT_COLUMNS: List[ColumnDef] = [
    # 账号限制为字母/数字/下划线，长度 2~64，避免出现中文或空格登录名。
    ColumnDef("登录账号*", "username", str, required=True, max_length=64,
              pattern=r"^[A-Za-z0-9_]{2,64}$", desc="字母数字下划线"),
    ColumnDef("姓名*", "real_name", str, required=True, max_length=64),
    # 密码列由 service 层在 create 时哈希，模板/导出都不会回显明文。
    ColumnDef("密码*", "password", str, required=True, max_length=64),
    ColumnDef("邮箱", "email", str, max_length=128),
    # 手机号用正则限定中国大陆号段，减少脏数据。
    ColumnDef("手机号", "phone", str, max_length=20, pattern=r"^1[3-9]\d{9}$"),
    # 角色用中文显示值导入，落库转成 1/2/3/4；与系统 RoleEnum 保持一致。
    ColumnDef("角色*", "role", int, required=True,
              choices={"学生": 1, "指导教师": 2, "评审专家": 3, "系统管理员": 4}),
    # 学院列填编码而非名称：名称可能重复/改动，编码是稳定主键映射。
    ColumnDef("学院编码*", "college_id", int, required=True,
              desc="请使用学院ID；可在学院列表中查询"),
    # 状态选填，缺省为启用，方便批量导入新账号后直接可用。
    ColumnDef("状态", "status", int, default=1, choices={"启用": 1, "禁用": 0}),
]

PROJECT_IMPORT_COLUMNS: List[ColumnDef] = [
    ColumnDef("项目名称*", "project_name", str, required=True, max_length=255),
    # 类型/级别与项目状态枚举分离，导入时只允许这三种类型与四级级别。
    ColumnDef("项目类型*", "project_type", int, required=True,
              choices={"创新训练": 1, "创业训练": 2, "创业实践": 3}),
    ColumnDef("项目级别*", "project_level", int, required=True,
              choices={"院级": 1, "校级": 2, "省级": 3, "国家级": 4}),
    ColumnDef("学院编码*", "college_id", int, required=True),
    # 负责人以学号（即登录账号）导入，由服务层再解析成 user_id；
    # 模板阶段无法校验账号是否存在，只能依赖后续导入校验。
    ColumnDef("负责人学号*", "leader_username", str, required=True,
              desc="系统中必须存在的学生账号"),
    # 指导教师选填：允许先导入项目，后续再由学院分配指导教师。
    ColumnDef("指导教师工号", "teacher_username", str, max_length=64),
    # 日期列支持 Excel 原生日期与 YYYY-MM-DD/YYYY/MM/DD 文本。
    ColumnDef("开始日期", "start_date", date),
    ColumnDef("结束日期", "end_date", date),
    # 金额用 Decimal，缺省 0；导入后仍由服务层做非负校验。
    ColumnDef("预算总额", "budget_amount", Decimal, default=Decimal("0")),
    ColumnDef("项目简介", "project_summary", str, max_length=5000),
]


# ====================================================================
# Excel 工具类
# ====================================================================
class ExcelHelper:
    """Excel 导入导出工具类。

    所有方法均为静态方法：工具类不持有状态，调用方无需实例化。
    导出统一返回 bytes，由路由层决定文件名与响应头；
    导入统一返回 (数据列表, 错误列表)，由 service 层决定入库或回显错误。
    """

    @staticmethod
    def _ensure_openpyxl():
        """openpyxl 是可选依赖，延迟到调用时检查，避免未安装时整个应用启动失败。

        :raises RuntimeError: 未安装时抛出，提示安装命令
        """
        if Workbook is None:
            raise RuntimeError("请先安装 openpyxl: pip install openpyxl")

    # ---------- 生成模板 ----------
    @staticmethod
    def generate_template(columns: List[ColumnDef], sheet_name: str = "Sheet1",
                          with_comments: bool = True) -> bytes:
        """
        根据列定义生成空白导入模板（含表头、下拉注释、示例行）
        :returns: xlsx 文件字节流

        :param columns: 列定义，决定表头文案、注释与列宽
        :param sheet_name: 工作表名（Excel 上限 31 字符，由调用方保证）
        :param with_comments: 是否在第 2 行写填写说明；为 True 时数据从第 3 行开始，
                              解析端 data_start_row 必须与之对应，否则会把说明行当数据。

        样式约定：深蓝底白字加粗表头、细边框、居中换行；
        注释行为灰色斜体；列宽按表头长度估算并夹在 12~50 之间。
        """
        ExcelHelper._ensure_openpyxl()
        wb = Workbook()
        ws = wb.active
        ws.title = sheet_name

        # 样式
        # 固定色值 4F81BD 与导出函数保持一致，模板与台账的视觉统一。
        header_font = Font(bold=True, color="FFFFFF", size=12)
        header_fill = PatternFill("solid", fgColor="4F81BD")
        thin_border = Border(
            left=Side(style="thin"), right=Side(style="thin"),
            top=Side(style="thin"), bottom=Side(style="thin"),
        )
        center = Alignment(horizontal="center", vertical="center", wrap_text=True)

        # 1. 表头
        # 只写第 1 行，不合并单元格：保证每个字段独占一列，解析位置固定。
        for col_idx, col in enumerate(columns, start=1):
            cell = ws.cell(row=1, column=col_idx, value=col.header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center
            cell.border = thin_border

        # 2. 注释行（第2行，说明）
        # 拼成「填写说明 | 可选值 | 必填/选填」，用户不查文档也能填对；
        # 该行不参与解析，由 data_start_row=3 跳过。
        if with_comments:
            for col_idx, col in enumerate(columns, start=1):
                parts = []
                if col.desc:
                    parts.append(col.desc)
                if col.choices:
                    parts.append("可选: " + "/".join(str(k) for k in col.choices.keys()))
                parts.append("必填" if col.required else "选填")
                cell = ws.cell(row=2, column=col_idx, value=" | ".join(parts))
                cell.font = Font(italic=True, color="666666", size=10)
                cell.alignment = Alignment(wrap_text=True, vertical="center")
                cell.border = thin_border

        # 3. 列宽自适应
        # openpyxl 不能真正测量内容宽度，按表头字符数 *2+4 估算；
        # 夹在 12~50 之间：过窄看不清中文，过宽会让多列表格横向滚动过长。
        for col_idx, col in enumerate(columns, start=1):
            width = max(12, min(50, len(col.header) * 2 + 4))
            ws.column_dimensions[get_column_letter(col_idx)].width = width
        # 冻结表头
        # 有注释行时冻结到第 3 行，滚动时表头与填写说明始终可见；否则只冻结第 1 行。
        ws.freeze_panes = "A3" if with_comments else "A2"

        # 写内存返回
        # 用 BytesIO 而非临时文件，多人并发下载模板时不会互相覆盖，也没有清理问题。
        buffer = io.BytesIO()
        wb.save(buffer)
        return buffer.getvalue()

    # ---------- 数据解析 ----------
    @staticmethod
    def parse_workbook(file_bytes: bytes, columns: List[ColumnDef],
                       header_row: int = 1, data_start_row: int = 3) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        解析上传的Excel文件为数据字典列表 + 错误信息
        :param file_bytes: 上传文件的bytes
        :param columns: 列定义（顺序必须与Excel列顺序一致）
        :param header_row: 表头所在行号
        :param data_start_row: 数据起始行（含），默认跳过注释行
        :returns: (成功解析的数据列表, 错误信息列表)

        :side effect: 只读文件内容、不落库；采用整表校验策略，
                      所有行的错误一次性汇总返回，用户不必反复上传。
        """
        ExcelHelper._ensure_openpyxl()
        errors: List[str] = []
        results: List[Dict[str, Any]] = []
        # data_only=True 让公式单元格返回计算结果而非公式文本；
        # 若文件未在 Excel 中计算过，公式列可能读到 None，属预期行为。
        try:
            buffer = io.BytesIO(file_bytes)
            wb = load_workbook(buffer, data_only=True, read_only=False)
            ws = wb.active
        except Exception as e:
            return [], [f"Excel文件读取失败: {e}"]

        # 表头校验
        # 只取前 len(columns) 列比对，忽略用户额外插入的空白列；
        # 比对前去掉 * 与首尾空格，允许填写「项目名称」或「项目名称*」。
        headers = [ws.cell(row=header_row, column=i).value for i in range(1, len(columns) + 1)]
        expected_headers = [c.header for c in columns]
        for idx, (h, exp) in enumerate(zip(headers, expected_headers)):
            # 去掉必填标记*对比
            norm_h = (str(h) if h else "").replace("*", "").strip()
            norm_exp = exp.replace("*", "").strip()
            if norm_h != norm_exp:
                errors.append(f"第{header_row}行第{idx + 1}列表头不匹配：期望'{exp}'，实际'{h}'")
        if errors:
            # 表头不对就整体拒绝：列错位时继续解析只会得到一批字段错位的数据。
            return [], errors

        # 逐行解析
        # ws.max_row 是实际使用的最大行，可能包含尾部空行，由 all_empty 过滤。
        max_row = ws.max_row or 0
        if max_row < data_start_row:
            return [], ["未检测到有效数据行"]

        for row_idx in range(data_start_row, max_row + 1):
            row_data: Dict[str, Any] = {}
            row_errors: List[str] = []
            all_empty = True
            for col_idx, col_def in enumerate(columns, start=1):
                raw = ws.cell(row=row_idx, column=col_idx).value
                value, err = col_def.validate(raw)
                # 任意一格有非空内容即视为有效行；strip 用于忽略「只敲空格」的行。
                if raw is not None and not (isinstance(raw, str) and raw.strip() == ""):
                    all_empty = False
                if err:
                    row_errors.append(f"列[{col_def.header}]: {err}")
                else:
                    row_data[col_def.field] = value
            if all_empty:
                continue  # 空行跳过
            # 有错误的行不进入结果集，但错误会累计到 errors，
            # 这样一次上传就能看到所有问题行，而不是修一行传一次。
            if row_errors:
                errors.append(f"第{row_idx}行: " + "；".join(row_errors))
            else:
                results.append(row_data)
        return results, errors

    # ---------- 多工作表导出 ----------
    @staticmethod
    def export_sheets(
        sheets: List[Tuple[str, List[Tuple[str, str, Optional[Callable]]], List[Dict[str, Any]]]],
    ) -> bytes:
        """
        将多个工作表导出为同一个 Excel 二进制
        sheets 示例: [("项目概况", [("字段", "k"), ("内容", "v")], rows), ...]

        :param sheets: 每个元素为 (工作表名, 列定义, 数据行)
        :return: xlsx 字节流
        :side effect: 全量数据在内存中组装。归档包需要「一次请求拿到多张关联表」，
                      避免前端逐表请求时数据快照不一致（导出期间数据被修改）。
        """
        ExcelHelper._ensure_openpyxl()
        wb = Workbook()
        # 删除默认空表，只保留调用方传入的工作表，避免导出文件多出一个空白 Sheet。
        wb.remove(wb.active)
        header_font = Font(bold=True, color="FFFFFF", size=11)
        header_fill = PatternFill("solid", fgColor="4F81BD")
        center = Alignment(horizontal="center", vertical="center", wrap_text=True)
        thin = Side(style="thin")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        for sheet_name, columns, data_rows in sheets:
            # 兼容 (表头, 字段) 与 (表头, 字段, 格式化函数) 两种列定义
            # 补 None 补齐为三元组，后续循环无需再判断长度。
            cols = [tuple(c) + (None,) * (3 - len(c)) for c in columns]
            # Excel 工作表名上限 31 字符，超长直接截断，否则 save 会抛异常。
            ws = wb.create_sheet(title=sheet_name[:31])
            for col_idx, (header, _, _) in enumerate(cols, start=1):
                cell = ws.cell(row=1, column=col_idx, value=header)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = center
                cell.border = border
                # 与 export_list 相同的最小列宽规则，保证多表导出的观感一致。
                ws.column_dimensions[get_column_letter(col_idx)].width = max(14, len(header) * 2 + 2)
            for r_idx, row in enumerate(data_rows, start=2):
                for c_idx, (_, field, fmt) in enumerate(cols, start=1):
                    # 同时支持 dict 与 ORM 对象：归档服务通常直接传模型实例。
                    val = row.get(field) if isinstance(row, dict) else getattr(row, field, None)
                    # 日期/金额/枚举名的格式化统一放在导出层做，失败时保留原值继续，
                    # 不能因为一格格式化失败让整个导出接口返回 500。
                    if fmt and val is not None:
                        try:
                            val = fmt(val)
                        except Exception:
                            pass
                    cell = ws.cell(row=r_idx, column=c_idx, value=val)
                    cell.alignment = Alignment(vertical="center", wrap_text=True)
                    cell.border = border
            ws.freeze_panes = "A2"

        buffer = io.BytesIO()
        wb.save(buffer)
        return buffer.getvalue()

    # ---------- 导出列表 ----------
    @staticmethod
    def export_list(
        columns: List[Tuple[str, str, Optional[Callable]]],  # [(表头, 字段或key, 格式化函数可选)]
        data_rows: List[Dict[str, Any]],
        sheet_name: str = "Sheet1",
    ) -> bytes:
        """
        将数据列表导出为Excel二进制
        columns 示例: [("项目名称", "project_name"), ("预算", "budget_amount", lambda v: f"¥{v:.2f}")]

        :param columns: 列定义；顺序即 Excel 列顺序
        :param data_rows: 数据行，支持 dict 或 ORM 对象
        :param sheet_name: 工作表名（超过 31 字符需调用方自行截断）
        :return: xlsx 字节流
        :side effect: 无。调用方应传入「按当前筛选条件的全量数据」而非当前页：
                      管理端导出用于线下核对/上报，只导当前页会缺数据；
                      因此导出接口独立于分页接口，不受 page_size 限制。
        """
        ExcelHelper._ensure_openpyxl()
        wb = Workbook()
        ws = wb.active
        ws.title = sheet_name
        header_font = Font(bold=True, color="FFFFFF", size=11)
        header_fill = PatternFill("solid", fgColor="4F81BD")
        center = Alignment(horizontal="center", vertical="center", wrap_text=True)
        thin = Side(style="thin")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        # 写表头
        # 列宽按表头长度估算，最小 14 保证两字中文表头不会挤在一起。
        for col_idx, (header, _, _) in enumerate(columns, start=1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center
            cell.border = border
            ws.column_dimensions[get_column_letter(col_idx)].width = max(14, len(header) * 2 + 2)

        # 写数据
        # 从第 2 行开始，freeze_panes=A2 让滚动时表头保持可见。
        for r_idx, row in enumerate(data_rows, start=2):
            for c_idx, (_, field, fmt) in enumerate(columns, start=1):
                val = row.get(field) if isinstance(row, dict) else getattr(row, field, None)
                if fmt and val is not None:
                    try:
                        val = fmt(val)
                    except Exception:
                        pass
                cell = ws.cell(row=r_idx, column=c_idx, value=val)
                cell.alignment = Alignment(vertical="center", wrap_text=True)
                cell.border = border
        ws.freeze_panes = "A2"
        buffer = io.BytesIO()
        wb.save(buffer)
        return buffer.getvalue()


# ====================================================================
# 常用导出：项目名单 / 经费台账 / 评审结果 / 操作日志 / 用户列表
# ====================================================================
class ExportTemplates:
    """预定义常用导出列，配合 export_list 使用。

    这里只声明「表头 -> 字段 -> 格式化函数」，数据由 service 层组装成 dict：
    枚举（类型/级别/角色/状态）在 service 层已转成 *_name 字段，
    因此本类无需重复维护角色与状态的映射表。

    格式约定：
        - 金额统一保留 2 位小数并转字符串（Decimal 计算，不用 float）；
        - 日期统一 yyyy-MM-dd（str(v) 对 date 即为该格式）；
        - 日期时间统一 yyyy-MM-dd HH:mm 或 HH:mm:ss，避免 Excel 把时间显示成序列号；
        - 空值一律输出空字符串，保证列宽与阅读体验稳定。
    """

    @staticmethod
    def project_list_columns():
        """项目名单导出列：覆盖编号、类型级别、负责人/教师、预算与状态。

        预算与已用金额用 Decimal(str(v or 0)) 再格式化：
        数据库可能返回 None 或 Decimal，先兜底 0 可避免 None 参与运算报错。
        """
        return [
            ("项目编号", "project_no", None),
            ("项目名称", "project_name", None),
            ("项目类型", "project_type_name", None),
            ("项目级别", "project_level_name", None),
            ("所属学院", "college_name", None),
            ("负责人", "leader_name", None),
            ("指导教师", "teacher_name", None),
            # 日期字段为 date 类型，str() 即 yyyy-MM-dd；空值输出空串而不是 "None"。
            ("开始日期", "start_date", lambda v: str(v) if v else ""),
            ("结束日期", "end_date", lambda v: str(v) if v else ""),
            ("预算(元)", "budget_amount", lambda v: f"{Decimal(str(v or 0)):.2f}"),
            ("已用(元)", "used_amount", lambda v: f"{Decimal(str(v or 0)):.2f}"),
            ("项目状态", "status_name", None),
            # 提交时间可能为空（草稿），格式化为到分钟并忽略秒，表格更紧凑。
            ("提交时间", "submit_time", lambda v: v.strftime("%Y-%m-%d %H:%M") if v else ""),
        ]

    @staticmethod
    def user_list_columns():
        """用户名单导出列：账号、姓名、角色、学院与状态。

        状态是 0/1，导出时转成中文「启用/禁用」，避免线下核对时还要查字典。
        注意：不导出密码或 password_hash。
        """
        return [
            ("账号", "username", None),
            ("姓名", "real_name", None),
            ("角色", "role_name", None),
            ("学院", "college_name", None),
            ("邮箱", "email", None),
            ("手机号", "phone", None),
            ("状态", "status", lambda v: "启用" if v == 1 else "禁用"),
            ("创建时间", "created_at", lambda v: v.strftime("%Y-%m-%d %H:%M") if v else ""),
        ]

    @staticmethod
    def operation_log_columns():
        """操作日志导出列：用于审计留档，时间精确到秒。

        审计场景要求可追溯到具体请求，因此保留请求方式、URL、IP、耗时与响应码；
        这些字段在页面表格里可能不展示，但导出时必须完整。
        """
        return [
            ("操作时间", "operation_time", lambda v: v.strftime("%Y-%m-%d %H:%M:%S") if v else ""),
            ("操作人", "real_name", None),
            ("账号", "username", None),
            ("模块", "module_name", None),
            ("操作类型", "operation_type", None),
            ("操作描述", "operation_desc", None),
            ("请求方式", "request_method", None),
            ("请求URL", "request_url", None),
            ("IP地址", "ip_address", None),
            ("耗时(ms)", "cost_time", None),
            ("响应码", "response_code", None),
        ]

    @staticmethod
    def review_result_columns():
        """评审结果导出列：项目 + 阶段 + 专家 + 评分/结果/意见。

        评分允许为空（占位记录未打分），因此用 is not None 判断而非真值，
        否则 0 分会被错误地导成空字符串。
        """
        return [
            ("项目编号", "project_no", None),
            ("项目名称", "project_name", None),
            ("学院", "college_name", None),
            ("评审阶段", "review_stage_name", None),
            ("评审专家", "reviewer_name", None),
            ("评分", "score", lambda v: f"{v}" if v is not None else ""),
            ("评审结果", "review_result_name", None),
            ("评审意见", "review_comment", None),
            ("评审时间", "review_time", lambda v: v.strftime("%Y-%m-%d %H:%M") if v else ""),
        ]
