"""
校园创新创业项目管理平台 - 真实数据种子脚本
用于生成毕业设计演示所需的真实业务数据
"""
import sys
import os
import random
import re
from datetime import datetime, date, timedelta
from decimal import Decimal

# 确保项目根目录在 sys.path 中
_PROJ_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _PROJ_ROOT)

from sqlalchemy.orm import Session
from app.database.session import SessionLocal, engine
from app.models.user import SysUser, SysCollege
from app.models.project import (
    ProjProject, ProjTeamMember, ProjReview, ProjBudget,
    ProjExpense, ProjAchievement, ProjMidtermCheck, ProjChangeRequest,
)
from app.models.competition import Competition

# 项目状态: 0-草稿 1-待学院初审 2-学院初审通过 3-待校级复审 4-校级复审通过
# 5-待专家评审 6-已立项 7-中期检查 8-待结题 9-已结题 10-已驳回 11-已撤销
# 审核阶段: 1-学院初审 2-校级复审 3-专家评审 4-结题验收
# 审核结果: 1-通过 2-驳回 3-修改后重提

# ==================== 真实项目模板 ====================
PROJECT_TEMPLATES = [
    {
        "name": "基于Vue+FastAPI的校园创新创业管理平台设计与实现",
        "type": 1, "level": 1,
        "summary": "本项目旨在开发一套面向高校的创新创业项目管理平台，采用Vue3+FastAPI技术栈，实现项目申报、审核、经费管理、成果登记等全流程数字化管理，提升高校创新创业工作的管理效率与信息化水平。",
        "innovation": "1.采用前后端分离架构，前端Vue3+Element Plus，后端FastAPI+SQLAlchemy，响应迅速、可扩展性强；2.集成AI智能助手，提供项目申报智能推荐、文本自动生成等辅助功能；3.支持多角色权限管理，涵盖学生、指导教师、评审专家、管理员四类角色的精细化权限控制。",
        "expected": "完成平台开发并部署上线，实现项目申报、审核、经费、成果等核心模块；发表学术论文1篇；申请软件著作权1项。",
    },
    {
        "name": "基于深度学习的校园智能安防监控系统",
        "type": 1, "level": 2,
        "summary": "针对传统校园安防监控依赖人工值守、响应滞后的问题，本项目设计并实现一套基于深度学习的智能安防监控系统。系统集成目标检测、行为识别、异常告警等功能，可对校园重点区域进行7×24小时智能监测，及时发现并预警安全隐患。",
        "innovation": "1.采用YOLOv8目标检测算法，结合校园场景数据集进行迁移学习，识别准确率达95%以上；2.设计多模态融合的异常行为识别模型，综合视频帧与音频特征进行联合判断；3.实现边缘端轻量化部署，支持在普通监控设备上实时运行。",
        "expected": "完成系统原型开发并在校园试点部署；申请发明专利1项、实用新型专利1项；发表EI会议论文1篇。",
    },
    {
        "name": "智慧农业物联网监测与精准灌溉系统",
        "type": 1, "level": 2,
        "summary": "面向现代农业精细化管理需求，开发一套基于物联网的智慧农业监测与精准灌溉系统。系统通过部署在田间的各类传感器实时采集土壤温湿度、光照强度、CO2浓度等环境数据，结合气象预报与作物生长模型，实现灌溉量的智能决策与自动控制。",
        "innovation": "1.设计低功耗无线传感器网络节点，采用休眠-唤醒机制延长电池寿命至2年以上；2.构建基于LSTM的作物需水量预测模型，灌溉决策准确率较传统方法提升30%；3.支持移动端远程监控与手动干预，农户可随时随地掌握农田状况。",
        "expected": "完成硬件原型与软件平台开发；在试验田部署验证节水率达25%以上；申请软件著作权2项、实用新型专利1项。",
    },
    {
        "name": "面向大学生的闲置物品共享交易平台",
        "type": 3, "level": 1,
        "summary": "针对大学校园闲置物品流通不畅、资源浪费严重的现状，打造一款专注于校园场景的闲置物品共享交易平台。平台提供二手书、电子产品、生活用品等品类的发布、搜索、交易功能，并引入信用评价与校园实名认证机制，保障交易安全。",
        "innovation": "1.创新采用基于地理位置与社交关系的推荐算法，优先展示同校及周边用户的闲置物品；2.设计物品溯源与真伪鉴别机制，针对电子产品提供序列号验证服务；3.推出以物易物功能，支持物品直接交换，降低交易门槛。",
        "expected": "完成平台开发并上线运营，注册用户突破5000人，月交易额达10万元；形成完整的商业计划书；冲击互联网+大学生创新创业大赛省级奖项。",
    },
    {
        "name": "基于区块链的高校学历证书存证系统",
        "type": 1, "level": 3,
        "summary": "针对传统学历证书易伪造、验证流程繁琐的痛点，设计并实现一套基于区块链技术的高校学历证书存证与验证系统。系统将证书关键信息上链存证，用人单位可通过扫码或输入证书编号快速验证真伪，有效杜绝学历造假。",
        "innovation": "1.采用联盟链架构，由高校、教育主管部门、用人单位共同组成验证节点，兼顾去中心化与权威性；2.设计基于零知识证明的隐私保护方案，验证方无需获取证书全文即可确认其真实性；3.支持批量上链与批量验证，满足高校毕业季大规模发证需求。",
        "expected": "完成系统设计与核心模块开发；在试点高校完成小规模部署验证；发表核心期刊论文1篇；申请发明专利1项。",
    },
    {
        "name": "智能语音交互的图书馆座位预约小程序",
        "type": 1, "level": 1,
        "summary": "为解决高校图书馆座位管理混乱、占座现象严重的问题，开发一款支持智能语音交互的图书馆座位预约微信小程序。学生可通过语音或文字查询空座、预约座位、临时离开、退座等，图书馆管理员可实时监控座位使用情况并进行管理。",
        "innovation": "1.集成智能语音识别与语义理解，支持自然语言座位查询，如三楼靠窗还有空位吗；2.设计基于用户行为画像的座位推荐算法，根据历史使用习惯推荐合适座位；3.引入信用积分机制，对违约占座行为进行约束。",
        "expected": "完成小程序开发并在校内图书馆试点运行，日活跃用户达800人以上；申请软件著作权1项；发表论文1篇。",
    },
    {
        "name": "基于机器视觉的工件表面缺陷检测系统",
        "type": 1, "level": 2,
        "summary": "面向制造业质检环节对自动化、高精度的需求，开发一套基于机器视觉的工件表面缺陷检测系统。系统通过工业相机采集工件表面图像，利用深度学习算法自动识别划痕、凹陷、污渍等缺陷类型并定位，实现质检环节的智能化升级。",
        "innovation": "1.设计多尺度特征融合的缺陷检测网络，对小尺寸缺陷的检出率达98%；2.提出基于迁移学习的少样本训练策略，仅需少量标注样本即可达到较高检测精度；3.支持在线实时检测，处理速度达30帧/秒，满足产线节拍要求。",
        "expected": "完成算法模型开发与检测系统搭建；在合作企业产线完成测试验证；申请发明专利1项、软件著作权1项。",
    },
    {
        "name": "校园二手教材循环利用服务平台",
        "type": 3, "level": 1,
        "summary": "针对高校教材使用周期短、浪费严重的问题，打造校园二手教材循环利用服务平台。平台连接毕业生与在校生，提供教材回收、消毒、租赁、转售等一体化服务，降低学生购书成本，推动绿色校园建设。",
        "innovation": "1.建立教材成色智能评估模型，通过拍照识别教材破损程度并给出回收估价；2.设计教材流通溯源系统，记录每本教材的流转历史，保障卫生安全；3.推出教材订阅制服务，学生按学期订阅所需教材，费用仅为新书的30%。",
        "expected": "完成平台开发与运营体系搭建；覆盖3所高校，回收教材2万册以上；形成可持续的商业模式。",
    },
    {
        "name": "基于增强现实的机械装配实训系统",
        "type": 1, "level": 3,
        "summary": "针对机械类专业实训设备昂贵、操作风险高的问题，开发一套基于增强现实（AR）技术的机械装配实训系统。学生佩戴AR设备即可在虚拟环境中完成齿轮箱、发动机等复杂机构的拆装训练，系统实时提供操作引导与错误纠正。",
        "innovation": "1.采用空间锚定技术实现虚拟模型与真实工作台的精准对齐，误差小于2mm；2.设计基于手势识别的自然交互方式，支持抓取、旋转、装配等操作；3.构建智能化评分系统，根据操作步骤的完整性与规范性自动打分。",
        "expected": "完成核心功能开发与3D模型制作；在机械工程学院实训课程中试点应用；申请发明专利1项、软件著作权2项。",
    },
    {
        "name": "面向独居老人的智能跌倒检测与报警手环",
        "type": 3, "level": 2,
        "summary": "针对独居老人跌倒后无法及时求助的社会痛点，研发一款集跌倒检测、健康监测、紧急报警于一体的智能手环。手环内置六轴加速度传感器与心率监测模块，可实时识别跌倒事件并自动通知紧急联系人与社区服务中心。",
        "innovation": "1.设计基于阈值判定与机器学习相结合的跌倒检测算法，灵敏度达99%，误报率低于1%；2.采用低功耗设计，单次充电续航达7天；3.集成一键SOS与语音通话功能，操作简单，适合老年人使用。",
        "expected": "完成手环硬件设计与配套APP开发；开展100人规模的用户测试；申请实用新型专利2项、外观专利1项。",
    },
    {
        "name": "基于知识图谱的高校就业推荐系统",
        "type": 1, "level": 1,
        "summary": "针对大学生就业信息不对称、人岗匹配度低的问题，构建基于知识图谱的高校就业推荐系统。系统整合岗位信息、毕业生画像、企业需求等多源数据，通过知识推理实现精准的人岗匹配与就业路径推荐。",
        "innovation": "1.构建涵盖岗位技能、专业课程、能力素质的就业知识图谱，实体规模超10万；2.设计基于图神经网络的推荐算法，推荐准确率较协同过滤方法提升20%；3.支持就业竞争力评估，为学生提供能力提升建议。",
        "expected": "完成系统开发与知识图谱构建；在就业指导中心试点应用；发表论文1篇、申请软件著作权1项。",
    },
    {
        "name": "校园无人配送小车路径规划与调度系统",
        "type": 1, "level": 2,
        "summary": "面向校园末端配送需求，开发一套无人配送小车的路径规划与多车调度系统。系统基于校园高精度地图，综合考虑配送时效、车辆载荷、障碍物等因素，为多辆配送小车生成最优配送路径并实现动态调度。",
        "innovation": "1.设计改进A*算法结合时间窗约束的路径规划方法，有效避免多车碰撞；2.提出基于遗传算法的订单分配与车辆调度优化策略，配送效率提升25%；3.支持实时路况更新与动态重规划，应对突发情况。",
        "expected": "完成算法开发与仿真验证；与校园快递合作开展小规模试运行；申请发明专利1项。",
    },
    {
        "name": "基于物联网的智能教室环境监测与调控系统",
        "type": 1, "level": 1,
        "summary": "针对传统教室环境监测手段落后、能耗浪费严重的问题，开发一套基于物联网技术的智能教室环境监测与调控系统。系统实时采集教室温度、湿度、CO2浓度、光照强度等参数，通过智能算法自动调节空调、照明、通风设备，为师生创造舒适的学习环境，同时降低能耗。",
        "innovation": "1.设计多传感器数据融合算法，提高环境参数监测精度；2.提出基于人体感应与课程表的智能调控策略，避免无人时段能源浪费；3.支持远程监控与手动控制，管理员可通过手机APP实时管理教室设备。",
        "expected": "完成系统原型开发与试点部署；实现节能率20%以上；申请软件著作权1项、实用新型专利1项。",
    },
]

# 团队角色模板
TEAM_ROLES = ["项目负责人", "前端开发", "后端开发", "算法工程师", "UI设计", "测试工程师", "文档撰写", "市场调研"]

# 预算科目模板
BUDGET_ITEMS = [
    ("设备费", "开发设备、服务器等硬件采购"),
    ("材料费", "实验耗材、原型制作、样品打样"),
    ("差旅费", "市场调研、用户访谈、学术交流差旅"),
    ("劳务费", "团队成员劳务与激励"),
    ("印刷费", "论文打印、资料印刷、展板制作"),
    ("测试化验加工费", "第三方检测、样品加工"),
    ("出版/文献/信息传播费", "论文版面费、专利申请费、数据库订阅"),
    ("其他费用", "会议注册费、培训费等"),
]

# 审核意见模板（学院初审）
COLLEGE_REVIEW_COMMENTS = [
    "项目选题具有实际意义，技术路线可行，团队配置合理，同意推荐上报。",
    "该项目结合专业特色，创新性较强，预算编制规范，建议通过初审。",
    "项目方案完整，预期成果明确，指导教师认真负责，同意报送校级复审。",
    "选题紧贴社会需求，前期调研充分，团队分工明确，同意推荐。",
    "项目具有较好的应用前景，技术方案合理，经费预算适当，同意通过。",
]

# 审核意见模板（校级复审）
SCHOOL_REVIEW_COMMENTS = [
    "项目技术含量较高，实施方案详实，具备立项条件，同意通过校级复审。",
    "该项目创新性突出，团队实力较强，经费预算合理，建议予以立项支持。",
    "项目符合校级创新创业项目立项要求，同意通过复审，进入专家评审环节。",
    "选题新颖，技术路线清晰，预期成果可量化，同意推荐专家评审。",
]

# 审核意见模板（专家评审）
EXPERT_REVIEW_COMMENTS = [
    "项目立意明确，技术方案先进可行，团队成员专业背景匹配度高，建议优先资助。综合评分：92分。",
    "该项目具有较强的实用价值和推广前景，研究内容充实，进度安排合理，同意立项。综合评分：88分。",
    "项目创新性较好，技术路线正确，预算编制合理，建议予以立项。综合评分：85分。",
    "选题具有前沿性，研究基础扎实，团队协作能力强，预期成果丰富，同意立项。综合评分：90分。",
]

# 成果模板
ACHIEVEMENT_TEMPLATES = {
    "paper": [
        {"title": "基于{}的研究与实现", "publisher": "计算机工程与应用", "level": 2},
        {"title": "{}关键技术研究", "publisher": "软件学报", "level": 3},
        {"title": "面向{}的优化方法", "publisher": "计算机科学", "level": 2},
    ],
    "patent": [
        {"title": "一种{}装置及方法", "achievement_no": "CN202610001234.X", "level": 2},
        {"title": "基于{}的系统及方法", "achievement_no": "CN202610005678.9", "level": 2},
    ],
    "software": [
        {"title": "{}系统V1.0", "achievement_no": "2026SR0123456", "level": 1},
        {"title": "{}平台软件", "achievement_no": "2026SR0789012", "level": 1},
    ],
    "award": [
        {"title": "中国国际大学生创新大赛省级银奖", "award_level": "省级银奖", "level": 2},
        {"title": "挑战杯全国大学生课外学术科技作品竞赛三等奖", "award_level": "国家级三等奖", "level": 3},
        {"title": "全国大学生数学建模竞赛省级一等奖", "award_level": "省级一等奖", "level": 2},
    ],
}

# 报销用途模板
EXPENSE_DESCS = [
    "购买开发用服务器1台",
    "实验耗材采购（传感器、电路板等）",
    "前往合作企业调研差旅费",
    "论文版面费支付",
    "专利申请代理费",
    "项目成员加班餐饮补贴",
    "打印项目申报书及答辩材料",
    "参加学术会议注册费",
]


def gen_project_no(seq: int) -> str:
    return f"IE2026{seq:06d}"


def pick_users(db: Session, role: int, count: int, exclude_ids=None):
    """从数据库中随机选取指定角色的用户"""
    exclude_ids = exclude_ids or []
    q = db.query(SysUser).filter(
        SysUser.role == role,
        SysUser.is_deleted == 0,
        SysUser.status == 1,
    )
    if exclude_ids:
        q = q.filter(~SysUser.id.in_(exclude_ids))
    users = q.all()
    return random.sample(users, min(count, len(users)))


def get_colleges(db: Session):
    return db.query(SysCollege).filter(SysCollege.is_deleted == 0).all()


def seed():
    db: Session = SessionLocal()
    try:
        # ==================== 清理旧数据 ====================
        print("[1/6] 清理旧的项目相关数据...")
        db.query(ProjChangeRequest).delete()
        db.query(ProjMidtermCheck).delete()
        db.query(ProjAchievement).delete()
        db.query(ProjExpense).delete()
        db.query(ProjBudget).delete()
        db.query(ProjReview).delete()
        db.query(ProjTeamMember).delete()
        db.query(ProjProject).delete()
        db.query(Competition).delete()
        db.commit()
        print("  -> 清理完成")

        # ==================== 获取基础数据 ====================
        colleges = get_colleges(db)
        college_ids = [c.id for c in colleges]

        # 获取各类用户
        students = db.query(SysUser).filter(
            SysUser.role == 1, SysUser.is_deleted == 0, SysUser.status == 1
        ).all()
        teachers = db.query(SysUser).filter(
            SysUser.role == 2, SysUser.is_deleted == 0, SysUser.status == 1
        ).all()
        experts = db.query(SysUser).filter(
            SysUser.role == 3, SysUser.is_deleted == 0, SysUser.status == 1
        ).all()
        admins = db.query(SysUser).filter(
            SysUser.role == 4, SysUser.is_deleted == 0, SysUser.status == 1
        ).all()

        print(f"  -> 用户数: 学生{len(students)} 教师{len(teachers)} 专家{len(experts)} 管理员{len(admins)}")

        # ==================== 创建竞赛 ====================
        print("[2/6] 创建竞赛数据...")
        competitions_data = [
            {
                "title": "第十三届中国国际大学生创新大赛",
                "competition_type": 4, "level": 3,
                "organizer": "教育部、中央统战部、中央网信办等",
                "co_organizer": "天津大学",
                "description": "中国国际大学生创新大赛是教育部等部门联合主办的全国性大学生创新创业赛事，旨在深化高等教育综合改革，激发大学生的创造力，培养造就大众创业、万众创新的生力军。",
                "requirements": "参赛对象为全日制在校学生（含本专科生、研究生）及毕业5年内的校友。项目需具有创新性、商业性和团队合作精神。",
                "rewards": "设高教主赛道、青年红色筑梦之旅、产业命题赛道等，各赛道分设金奖、银奖、铜奖。",
                "registration_start": date(2026, 4, 1),
                "registration_end": date(2026, 6, 30),
                "competition_start": date(2026, 7, 1),
                "competition_end": date(2026, 10, 31),
                "location": "天津市",
                "contact": "010-6609XXXX",
                "cover_image": "/images/competitions/poster_internet_plus.jpg",
                "status": 1,
                "created_by": admins[0].id if admins else None,
            },
            {
                "title": "第十八届挑战杯全国大学生课外学术科技作品竞赛",
                "competition_type": 4, "level": 3,
                "organizer": "共青团中央、中国科协、教育部、中国社会科学院、全国学联",
                "co_organizer": "复旦大学",
                "description": "挑战杯全国大学生课外学术科技作品竞赛是由共青团中央、中国科协、教育部、中国社会科学院、全国学联共同主办的全国性大学生课外学术实践竞赛。",
                "requirements": "参赛作品分为自然科学类学术论文、哲学社会科学类社会调查报告和学术论文、科技发明制作三大类。",
                "rewards": "设特等奖、一等奖、二等奖、三等奖，另设优秀组织奖、优秀指导教师奖等。",
                "registration_start": date(2026, 3, 1),
                "registration_end": date(2026, 5, 31),
                "competition_start": date(2026, 6, 1),
                "competition_end": date(2026, 11, 30),
                "location": "上海市",
                "contact": "010-8521XXXX",
                "cover_image": "/images/competitions/poster_tiaozhanbei.jpg",
                "status": 1,
                "created_by": admins[0].id if admins else None,
            },
            {
                "title": "2026年全国大学生数学建模竞赛",
                "competition_type": 3, "level": 3,
                "organizer": "中国工业与应用数学学会",
                "co_organizer": "中国海洋大学",
                "description": "全国大学生数学建模竞赛是教育部高教司和中国工业与应用数学学会共同主办的面向全国大学生的群众性科技活动。",
                "requirements": "参赛队由三名在校本科生组成，专业不限。竞赛期间可查阅图书资料、使用计算机和互联网，但不得与队外任何人讨论。",
                "rewards": "设一等奖、二等奖、三等奖，各等级比例分别不超过参赛队数的3%、7%、20%。",
                "registration_start": date(2026, 5, 1),
                "registration_end": date(2026, 8, 31),
                "competition_start": date(2026, 9, 11),
                "competition_end": date(2026, 9, 14),
                "location": "线上",
                "contact": "010-6278XXXX",
                "cover_image": "/images/competitions/poster_math_modeling.jpg",
                "status": 1,
                "created_by": admins[0].id if admins else None,
            },
            {
                "title": "2026年校级大学生创新创业训练计划项目申报",
                "competition_type": 1, "level": 1,
                "organizer": "校创新创业学院",
                "co_organizer": "各二级学院",
                "description": "校级大学生创新创业训练计划项目旨在促进高校转变教育思想观念，改革人才培养模式，强化创新创业能力训练，增强高校学生的创新能力和在创新基础上的创业能力。",
                "requirements": "项目分为创新训练项目、创业训练项目和创业实践项目三类。申请人为全日制在校本科生，团队人数3-5人。",
                "rewards": "创新训练项目资助1-2万元/项，创业训练项目资助2-3万元/项，创业实践项目资助5-10万元/项。",
                "registration_start": date(2026, 9, 1),
                "registration_end": date(2026, 9, 30),
                "competition_start": date(2026, 10, 1),
                "competition_end": date(2027, 9, 30),
                "location": "本校",
                "contact": "0571-8888XXXX",
                "cover_image": "/images/competitions/poster_school_training.jpg",
                "status": 1,
                "created_by": admins[0].id if admins else None,
            },
            {
                "title": "第十届浙江省大学生创新创业大赛",
                "competition_type": 4, "level": 2,
                "organizer": "浙江省教育厅、浙江省人力资源和社会保障厅",
                "co_organizer": "浙江大学",
                "description": "浙江省大学生创新创业大赛是浙江省内规模最大、影响力最广的大学生创新创业赛事，涵盖创新、创业、创意等多个赛道。",
                "requirements": "浙江省内全日制普通高校在校学生（含研究生）及毕业5年内的校友均可参赛。",
                "rewards": "设一等奖、二等奖、三等奖及优秀组织奖，获奖项目可获创业孵化支持。",
                "registration_start": date(2026, 4, 15),
                "registration_end": date(2026, 6, 15),
                "competition_start": date(2026, 7, 1),
                "competition_end": date(2026, 9, 30),
                "location": "杭州市",
                "contact": "0571-8795XXXX",
                "cover_image": "/images/competitions/poster_zhejiang_cxcy.jpg",
                "status": 1,
                "created_by": admins[0].id if admins else None,
            },
            {
                "title": "中国创新创业大赛",
                "competition_type": 2, "level": 3,
                "organizer": "科技部、财政部、教育部、中央网信办、全国工商联",
                "co_organizer": "科技部火炬高技术产业开发中心",
                "description": "中国创新创业大赛是由科技部、财政部、教育部、中央网信办和全国工商联共同指导举办的全国性创新创业赛事，是国内规格最高、规模最大、影响力最广的创新创业品牌活动。",
                "requirements": "参赛企业应为符合国家划型标准的中小企业，且注册时间不超过5年；团队组应拥有核心技术或创新产品，具有较好的商业前景。",
                "rewards": "设一等奖、二等奖、三等奖及优胜奖，获奖项目可获得国家创新创业政策支持、创业投资对接、孵化场地等扶持。",
                "registration_start": date(2026, 5, 1),
                "registration_end": date(2026, 7, 31),
                "competition_start": date(2026, 8, 1),
                "competition_end": date(2026, 11, 30),
                "location": "北京市",
                "contact": "010-8865XXXX",
                "cover_image": "/images/competitions/poster_cxcyds.jpg",
                "status": 1,
                "created_by": admins[0].id if admins else None,
            },
            {
                "title": "\"创青春\"全国大学生创业大赛",
                "competition_type": 2, "level": 3,
                "organizer": "共青团中央、教育部、人力资源和社会保障部、中国科协、全国学联",
                "co_organizer": "承办高校",
                "description": "\"创青春\"全国大学生创业大赛是由共青团中央等单位共同主办的全国性大学生创业实践赛事，旨在引导和激励大学生弘扬创新精神，提升创业能力，培养创业人才。",
                "requirements": "参赛对象为全国全日制普通高校在校学生（含本专科生、研究生）及毕业3年内的校友。参赛项目分为创业计划竞赛、创业实践挑战赛、公益创业赛等类别。",
                "rewards": "设金奖、银奖、铜奖，另设最佳创意奖、最具人气奖、优秀组织奖等。获奖项目可获得创业孵化、投资对接等支持。",
                "registration_start": date(2026, 3, 15),
                "registration_end": date(2026, 6, 30),
                "competition_start": date(2026, 7, 15),
                "competition_end": date(2026, 10, 15),
                "location": "线上+线下",
                "contact": "010-6707XXXX",
                "cover_image": "/images/competitions/poster_chuangqingchun.jpg",
                "status": 1,
                "created_by": admins[0].id if admins else None,
            },
            {
                "title": "全国大学生电子商务\"创新、创意及创业\"挑战赛",
                "competition_type": 2, "level": 3,
                "organizer": "教育部高等学校电子商务类专业教学指导委员会",
                "co_organizer": "承办高校",
                "description": "全国大学生电子商务\"创新、创意及创业\"挑战赛（简称\"三创赛\"）是由教育部高等学校电子商务类专业教学指导委员会主办的全国性大学生学科竞赛，旨在激发大学生的创新意识、创意思维和创业能力。",
                "requirements": "参赛队由3-5名在校本科生组成，配1-2名指导教师。参赛作品需围绕电子商务主题，具有创新性、创意性和可落地性。",
                "rewards": "设特等奖、一等奖、二等奖、三等奖及最佳创新奖、最佳创意奖、最佳创业奖等单项奖。",
                "registration_start": date(2026, 4, 1),
                "registration_end": date(2026, 6, 30),
                "competition_start": date(2026, 7, 1),
                "competition_end": date(2026, 10, 31),
                "location": "线上+线下",
                "contact": "010-6228XXXX",
                "cover_image": "/images/competitions/poster_ec_san_chuang.jpg",
                "status": 1,
                "created_by": admins[0].id if admins else None,
            },
            {
                "title": "\"中国创翼\"创业创新大赛",
                "competition_type": 2, "level": 3,
                "organizer": "人力资源和社会保障部、国家发展改革委、科技部、共青团中央、中国残联",
                "co_organizer": "承办地方人社部门",
                "description": "\"中国创翼\"创业创新大赛是由人力资源和社会保障部等部门联合主办的全国性创业创新赛事，旨在营造创新创业氛围，激发创业创新热情，助力创业带动就业。",
                "requirements": "参赛项目分为主体赛和专项赛。主体赛面向各类创业群体，专项赛面向青年、农民工、退役军人、残疾人等特定群体。项目需具有创新性和可持续性。",
                "rewards": "设一等奖、二等奖、三等奖及优胜奖，获奖项目可获得创业担保贷款、创业补贴、孵化服务等政策扶持。",
                "registration_start": date(2026, 4, 1),
                "registration_end": date(2026, 7, 15),
                "competition_start": date(2026, 8, 1),
                "competition_end": date(2026, 11, 15),
                "location": "全国各赛区",
                "contact": "010-8422XXXX",
                "cover_image": "/images/competitions/poster_zhongguochuangyi.jpg",
                "status": 1,
                "created_by": admins[0].id if admins else None,
            },
            {
                "title": "iCAN国际创新创业大赛",
                "competition_type": 4, "level": 3,
                "organizer": "iCAN国际创新创业大赛组委会",
                "co_organizer": "国际MEMS协会、中国微米纳米技术学会",
                "description": "iCAN国际创新创业大赛是由国际MEMS协会和中国微米纳米技术学会联合发起的国际性创新创业赛事，聚焦微纳米技术、物联网、人工智能等前沿科技领域的创新应用。",
                "requirements": "参赛对象为国内外高校在校学生及毕业3年内的青年创业者。参赛作品需基于微纳技术或相关前沿科技，具有创新性和应用价值。",
                "rewards": "设特等奖、一等奖、二等奖、三等奖及最佳创新奖、最具商业价值奖等。获奖项目可获得国际交流、产业对接、投资孵化等支持。",
                "registration_start": date(2026, 3, 1),
                "registration_end": date(2026, 6, 30),
                "competition_start": date(2026, 7, 1),
                "competition_end": date(2026, 10, 31),
                "location": "线上+国际赛区",
                "contact": "010-8264XXXX",
                "cover_image": "/images/competitions/poster_ican.jpg",
                "status": 1,
                "created_by": admins[0].id if admins else None,
            },
            {
                "title": "全国大学生创新体验竞赛",
                "competition_type": 1, "level": 3,
                "organizer": "中国高等教育学会",
                "co_organizer": "承办高校",
                "description": "全国大学生创新体验竞赛是由中国高等教育学会主办的全国性大学生创新实践赛事，强调\"创新体验\"理念，鼓励大学生通过亲身体验发现问题、提出创意、完成创新作品。",
                "requirements": "参赛对象为全国高校在校本科生。竞赛分为创新作品类、创新方法论类等赛道，参赛作品需体现创新思维和实践过程。",
                "rewards": "设特等奖、一等奖、二等奖、三等奖及优秀组织奖、优秀指导教师奖。",
                "registration_start": date(2026, 3, 15),
                "registration_end": date(2026, 5, 31),
                "competition_start": date(2026, 6, 15),
                "competition_end": date(2026, 9, 30),
                "location": "线上+线下",
                "contact": "025-8379XXXX",
                "cover_image": "/images/competitions/poster_innovation_experience.jpg",
                "status": 1,
                "created_by": admins[0].id if admins else None,
            },
            {
                "title": "浙江省\"挑战杯\"大学生创业计划竞赛",
                "competition_type": 2, "level": 2,
                "organizer": "共青团浙江省委、浙江省教育厅、浙江省科协、浙江省学联",
                "co_organizer": "承办高校",
                "description": "浙江省\"挑战杯\"大学生创业计划竞赛是浙江省内级别最高的大学生创业赛事，作为全国\"挑战杯\"创业计划竞赛的省级选拔赛，选拔优秀项目代表浙江省参加全国总决赛。",
                "requirements": "参赛对象为浙江省内全日制普通高校在校学生（含研究生）及毕业3年内的校友。参赛项目需具有完整的商业计划和可行性。",
                "rewards": "设金奖、银奖、铜奖及优秀组织奖。获奖项目将推荐参加全国\"挑战杯\"创业计划竞赛，并可获得省级创业扶持。",
                "registration_start": date(2026, 3, 1),
                "registration_end": date(2026, 5, 15),
                "competition_start": date(2026, 6, 1),
                "competition_end": date(2026, 9, 30),
                "location": "杭州市",
                "contact": "0571-8705XXXX",
                "cover_image": "/images/competitions/poster_zhejiang_tiaozhan.jpg",
                "status": 1,
                "created_by": admins[0].id if admins else None,
            },
            {
                "title": "2026年校级大学生创新创业大赛",
                "competition_type": 4, "level": 1,
                "organizer": "哈尔滨信息工程学院创新创业学院",
                "co_organizer": "各二级学院",
                "description": "校级大学生创新创业大赛面向全校在读学生，鼓励跨专业组队，重点考察项目的创新性、可行性与社会价值，是学校选拔省级、国家级赛事参赛项目的通道。",
                "requirements": "全日制在校本科生均可报名，团队3-5人（含负责人），须有指导教师；同一项目不得重复报名。",
                "rewards": "设校级一等奖、二等奖、三等奖及参与奖，颁发校级获奖证书并计入创新创业学分。",
                "registration_start": date(2026, 3, 1),
                "registration_end": date(2026, 5, 31),
                "competition_start": date(2026, 6, 1),
                "competition_end": date(2026, 8, 31),
                "location": "本校",
                "contact": "0451-8888XXXX",
                "cover_image": "/images/competitions/poster_school_cxcy.jpg",
                "status": 3,
                "created_by": admins[0].id if admins else None,
            },
        ]
        comp_objs = []
        for cd in competitions_data:
            # 届次按比赛开始年份推导（无则用报名开始年份）
            ref = cd.get("competition_start") or cd.get("registration_start")
            cd["session"] = f"{ref.year}届" if ref else None
            comp = Competition(**cd)
            db.add(comp)
            comp_objs.append(comp)
        db.commit()
        print(f"  -> 创建了 {len(comp_objs)} 个竞赛")

        # ==================== 创建项目 ====================
        print("[3/6] 创建项目数据...")
        # 项目状态分布：草稿2个, 待审核4个, 已立项及之后6个, 已驳回1个
        status_plan = [0, 0, 1, 3, 5, 12, 6, 6, 7, 8, 9, 9, 10]

        used_students = set()
        project_objs = []

        for idx, template in enumerate(PROJECT_TEMPLATES):
            # 随机选择负责人学生
            available_students = [s for s in students if s.id not in used_students]
            if not available_students:
                available_students = students
                used_students.clear()
            leader = random.choice(available_students)
            used_students.add(leader.id)

            # 选择同学院或任意学院的指导教师
            college_id = leader.college_id if leader.college_id else random.choice(college_ids)
            college_teachers = [t for t in teachers if t.college_id == college_id]
            teacher = random.choice(college_teachers) if college_teachers else random.choice(teachers)

            # 选择竞赛
            competition = random.choice(comp_objs) if random.random() > 0.3 else None

            # 状态
            status = status_plan[idx] if idx < len(status_plan) else random.choice([6, 7, 8, 9])

            # 预算
            budget_total = random.choice([10000, 15000, 20000, 25000, 30000, 50000])

            # 时间
            start_date = date(2026, 3, 1) + timedelta(days=random.randint(0, 60))
            end_date = start_date + timedelta(days=random.randint(180, 365))

            # 提交与审批时间
            submit_time = None
            approval_time = None
            current_approver_id = None
            reject_reason = None

            if status >= 1:  # 已提交
                submit_time = datetime.combine(start_date - timedelta(days=random.randint(5, 15)),
                                               datetime.min.time()).replace(hour=random.randint(8, 18))
            if status >= 6:  # 已立项
                approval_time = submit_time + timedelta(days=random.randint(30, 60))
                approval_time = approval_time.replace(hour=random.randint(9, 17))

            if status == 1:
                current_approver_id = teacher.id
            elif status in (2, 3):
                # 学院管理员
                college_admin = next((a for a in admins if a.college_id == college_id), admins[0] if admins else None)
                current_approver_id = college_admin.id if college_admin else None
            elif status in (4, 5):
                current_approver_id = admins[0].id if admins else None

            if status == 10:  # 驳回
                reject_reason = "项目预算明细不清晰，建议补充具体费用说明后重新提交。"

            proj = ProjProject(
                project_no=gen_project_no(idx + 1) if status >= 1 else None,
                project_name=template["name"],
                project_type=template["type"],
                project_level=template["level"],
                college_id=college_id,
                leader_id=leader.id,
                teacher_id=teacher.id,
                competition_id=competition.id if competition else None,
                competition_session=competition.session if competition else None,
                start_date=start_date,
                end_date=end_date,
                budget_amount=Decimal(str(budget_total)),
                used_amount=Decimal(str(round(budget_total * random.uniform(0.0, 0.6), 2))) if status >= 6 else Decimal("0.00"),
                project_summary=template["summary"],
                innovation_points=template["innovation"],
                expected_results=template["expected"],
                status=status,
                submit_time=submit_time,
                approval_time=approval_time,
                current_approver_id=current_approver_id,
                reject_reason=reject_reason,
            )
            db.add(proj)
            project_objs.append((proj, leader, teacher, college_id, budget_total))

        db.commit()
        print(f"  -> 创建了 {len(project_objs)} 个项目")

        # ==================== 团队成员、预算、审核 ====================
        print("[4/6] 创建团队成员、预算、审核记录...")
        for proj, leader, teacher, college_id, budget_total in project_objs:
            # --- 团队成员 ---
            # 负责人作为第一个成员
            leader_member = ProjTeamMember(
                project_id=proj.id,
                student_id=leader.id,
                student_name=leader.real_name,
                student_no=leader.username,
                major=f"{proj.college.college_name if proj.college else '计算机'}相关专业",
                grade="2023",
                role_in_team="项目负责人",
                task_desc="项目整体规划、技术方案设计、进度管理与对外沟通",
            )
            db.add(leader_member)

            # 额外3-5名成员
            member_count = random.randint(3, 5)
            member_students = pick_users(db, 1, member_count, exclude_ids=[leader.id])
            for ms in member_students:
                role = random.choice(TEAM_ROLES[1:])
                task_map = {
                    "前端开发": "负责前端页面开发与交互实现",
                    "后端开发": "负责后端API设计与数据库开发",
                    "算法工程师": "负责核心算法研究与模型训练",
                    "UI设计": "负责界面设计与用户体验优化",
                    "测试工程师": "负责系统测试与质量保证",
                    "文档撰写": "负责项目文档编写与资料整理",
                    "市场调研": "负责市场分析与用户调研",
                }
                member = ProjTeamMember(
                    project_id=proj.id,
                    student_id=ms.id,
                    student_name=ms.real_name,
                    student_no=ms.username,
                    major=f"{ms.college.college_name if ms.college else '相关'}专业",
                    grade="2023",
                    role_in_team=role,
                    task_desc=task_map.get(role, "协助项目开发"),
                )
                db.add(member)

            # --- 预算 ---
            # 3-5个预算科目
            budget_count = random.randint(3, 5)
            budget_items_selected = random.sample(BUDGET_ITEMS, budget_count)
            remaining = budget_total
            for i, (item_name, item_remark) in enumerate(budget_items_selected):
                if i == budget_count - 1:
                    amount = remaining
                else:
                    max_amt = int(remaining * 0.5)
                    amount = random.randint(1000, max(1000, max_amt))
                    remaining -= amount
                budget = ProjBudget(
                    project_id=proj.id,
                    budget_item=item_name,
                    budget_amount=Decimal(str(amount)),
                    used_amount=Decimal(str(round(amount * random.uniform(0.0, 0.5), 2))) if proj.status >= 6 else Decimal("0.00"),
                    remark=item_remark,
                )
                db.add(budget)

            # --- 审核记录 ---
            # 严格按"项目状态 → 已完成阶段"生成，避免记录与状态错位
            # （错位会导致待审核人打开项目后点通过时被 exist_real_review 拦截，
            #   提示"您已在该阶段审核过此项目"，审核流程无法进行）
            # 状态：0草稿 12待指导教师确认 1待学院初审 3待校级复审 5待专家评审
            #      6已立项 7中期 8待结题 9已结题 10已驳回
            college_admin = next((a for a in admins if a.college_id == college_id),
                                 admins[0] if admins else None)
            school_admin = admins[0] if admins else teacher

            # 指导教师确认(阶段0)：状态≥1 且已通过指导教师的（已驳回10 未通过，不写通过记录）
            if proj.status not in (0, 10, 12):
                db.add(ProjReview(
                    project_id=proj.id,
                    review_stage=0,
                    reviewer_id=teacher.id,
                    reviewer_name=teacher.real_name,
                    review_result=1,
                    review_comment=random.choice(COLLEGE_REVIEW_COMMENTS),
                    review_time=proj.submit_time + timedelta(days=random.randint(1, 2)),
                ))

            # 学院初审(阶段1)：状态≥3（待校级复审及以后）说明学院初审已通过
            if proj.status in (3, 5, 6, 7, 8, 9):
                db.add(ProjReview(
                    project_id=proj.id,
                    review_stage=1,
                    reviewer_id=college_admin.id if college_admin else teacher.id,
                    reviewer_name=college_admin.real_name if college_admin else teacher.real_name,
                    review_result=1,
                    review_comment=random.choice(COLLEGE_REVIEW_COMMENTS),
                    review_time=proj.submit_time + timedelta(days=random.randint(2, 5)),
                ))

            # 校级复审(阶段2)：状态≥5（待专家评审及以后）说明校级复审已通过
            if proj.status in (5, 6, 7, 8, 9):
                db.add(ProjReview(
                    project_id=proj.id,
                    review_stage=2,
                    reviewer_id=school_admin.id,
                    reviewer_name=school_admin.real_name,
                    review_result=1,
                    review_comment=random.choice(SCHOOL_REVIEW_COMMENTS),
                    review_time=proj.submit_time + timedelta(days=random.randint(8, 15)),
                ))

            # 专家评审(阶段3)：立项及以后=已完成评审；待专家评审(5)=只写占位(99)待评
            if proj.status in (6, 7, 8, 9):
                expert = random.choice(experts)
                score = Decimal(str(random.randint(80, 95)))
                comment = random.choice(EXPERT_REVIEW_COMMENTS)
                comment = re.sub(r'综合评分：\d+分', f'综合评分：{score}分', comment)
                db.add(ProjReview(
                    project_id=proj.id,
                    review_stage=3,
                    reviewer_id=expert.id,
                    reviewer_name=expert.real_name,
                    review_result=1,
                    score=score,
                    review_comment=comment,
                    review_time=proj.submit_time + timedelta(days=random.randint(15, 30)),
                ))
            elif proj.status == 5:
                # 待专家评审：为1-2位专家写入占位记录(99=已分配未评审)，供专家端打分
                for expert in random.sample(experts, random.randint(1, 2)):
                    db.add(ProjReview(
                        project_id=proj.id,
                        review_stage=3,
                        reviewer_id=expert.id,
                        reviewer_name=expert.real_name,
                        review_result=99,
                        score=None,
                        review_comment=None,
                        review_time=proj.submit_time + timedelta(days=random.randint(15, 30)),
                    ))

            # 已驳回(10)：补一条「指导教师驳回」记录（阶段0）用于展示驳回原因；
            # 该驳回为软门槛，学生可修改后重新提交（学院/校级/专家驳回则为终局落选，不在此造数）
            if proj.status == 10:
                db.add(ProjReview(
                    project_id=proj.id,
                    review_stage=0,
                    reviewer_id=teacher.id,
                    reviewer_name=teacher.real_name,
                    review_result=2,
                    review_comment=proj.reject_reason,
                    review_time=proj.submit_time + timedelta(days=random.randint(1, 3)),
                ))

        db.commit()
        print("  -> 团队成员、预算、审核记录创建完成")

        # ==================== 成果、报销、中期检查 ====================
        print("[5/6] 创建成果、报销、中期检查数据...")
        for proj, leader, teacher, college_id, budget_total in project_objs:
            # 成果（已立项及以后的项目才有成果）
            if proj.status >= 6:
                # 每个项目 1-3 个成果
                ach_count = random.randint(1, 3)
                proj_name_short = proj.project_name[:20]

                for _ in range(ach_count):
                    ach_type = random.choice([1, 1, 2, 3, 3, 4])  # 论文和软著偏多
                    if ach_type == 1:  # 论文
                        tpl = random.choice(ACHIEVEMENT_TEMPLATES["paper"])
                        ach = ProjAchievement(
                            project_id=proj.id,
                            achievement_type=1,
                            title=tpl["title"].format(proj_name_short),
                            author=leader.real_name,
                            publish_date=proj.start_date + timedelta(days=random.randint(100, 300)),
                            publisher=tpl["publisher"],
                            level=tpl["level"],
                            summary=f"本文围绕{proj_name_short}的关键技术开展研究，提出了创新性解决方案，并通过实验验证了方法的有效性。",
                        )
                    elif ach_type == 2:  # 专利
                        tpl = random.choice(ACHIEVEMENT_TEMPLATES["patent"])
                        ach = ProjAchievement(
                            project_id=proj.id,
                            achievement_type=2,
                            title=tpl["title"].format(proj_name_short),
                            author=f"{leader.real_name}等",
                            publish_date=proj.start_date + timedelta(days=random.randint(60, 200)),
                            publisher="国家知识产权局",
                            achievement_no=tpl["achievement_no"],
                            level=tpl["level"],
                            summary=f"本发明公开了一种{proj_name_short}相关的装置及方法，解决了现有技术中存在的问题。",
                        )
                    elif ach_type == 3:  # 软件著作权
                        tpl = random.choice(ACHIEVEMENT_TEMPLATES["software"])
                        ach = ProjAchievement(
                            project_id=proj.id,
                            achievement_type=3,
                            title=tpl["title"].format(proj_name_short),
                            author=leader.real_name,
                            publish_date=proj.start_date + timedelta(days=random.randint(30, 150)),
                            publisher="中国版权保护中心",
                            achievement_no=tpl["achievement_no"],
                            level=tpl["level"],
                            summary=f"{proj_name_short}系统软件，具备完整的功能模块，已通过软件著作权登记。",
                        )
                    else:  # 竞赛获奖
                        tpl = random.choice(ACHIEVEMENT_TEMPLATES["award"])
                        ach = ProjAchievement(
                            project_id=proj.id,
                            achievement_type=4,
                            title=tpl["title"],
                            author=f"{leader.real_name}团队",
                            publish_date=proj.start_date + timedelta(days=random.randint(120, 300)),
                            publisher="竞赛组委会",
                            level=tpl["level"],
                            award_level=tpl["award_level"],
                            summary=f"项目团队在{tpl['title']}中表现优异，荣获{proj_name_short}相关赛道的{tpl['award_level']}。",
                        )
                    db.add(ach)

            # 报销（已立项的项目有报销记录）
            if proj.status >= 6:
                exp_count = random.randint(2, 4)
                budgets = db.query(ProjBudget).filter(ProjBudget.project_id == proj.id).all()
                for _ in range(exp_count):
                    budget = random.choice(budgets) if budgets else None
                    exp_amount = random.randint(500, 3000)
                    exp_status = random.choice([2, 4, 6, 6])  # 偏已完成
                    exp = ProjExpense(
                        expense_no=f"EXP{proj.id:04d}{random.randint(1000,9999)}",
                        project_id=proj.id,
                        applicant_id=leader.id,
                        applicant_name=leader.real_name,
                        expense_amount=Decimal(str(exp_amount)),
                        budget_item_id=budget.id if budget else None,
                        expense_desc=random.choice(EXPENSE_DESCS),
                        invoice_no=f"INV{random.randint(10000000,99999999)}",
                        status=exp_status,
                        submit_time=proj.approval_time + timedelta(days=random.randint(10, 60)) if proj.approval_time else None,
                        approval_time=proj.approval_time + timedelta(days=random.randint(15, 70)) if exp_status == 6 and proj.approval_time else None,
                    )
                    db.add(exp)

            # 中期检查（中期检查及以后状态的项目）
            if proj.status >= 7:
                mid_status = 2 if proj.status >= 8 else random.choice([1, 2])
                mc = ProjMidtermCheck(
                    project_id=proj.id,
                    progress_desc="项目按计划推进，已完成系统架构设计、核心模块开发与初步测试。前端界面开发完成80%，后端API接口开发完成90%，数据库设计已全部完成。",
                    completed_tasks="1.完成需求分析与系统设计文档；2.完成数据库表结构设计与实现；3.完成核心功能模块的编码实现；4.完成单元测试与集成测试。",
                    remaining_tasks="1.完成剩余前端页面开发与联调；2.开展系统性能优化与安全测试；3.撰写项目中期报告与相关论文；4.准备结题验收材料。",
                    problems="部分第三方服务接口不稳定，影响联调进度；移动端适配需进一步优化。",
                    next_plan="1.加快前端页面开发进度，确保按期完成；2.完善异常处理与日志记录；3.启动论文撰写工作。",
                    budget_usage=Decimal(str(round(budget_total * 0.45, 2))),
                    status=mid_status,
                    reviewer_id=teacher.id,
                    review_comment="项目进展符合预期，团队协作良好，经费使用合理。建议继续按计划推进，注意把控后期质量。" if mid_status == 2 else None,
                    review_time=proj.approval_time + timedelta(days=random.randint(60, 90)) if proj.approval_time else None,
                    submit_time=proj.approval_time + timedelta(days=random.randint(55, 85)) if proj.approval_time else None,
                )
                db.add(mc)

            # 变更申请（部分已立项项目有延期申请）
            if proj.status >= 6 and random.random() > 0.6:
                cr = ProjChangeRequest(
                    project_id=proj.id,
                    change_type=random.choice([1, 3, 4]),
                    change_reason="因项目技术方案调整，部分任务进度略有滞后，申请延期一个月以确保项目质量。",
                    original_content=f"原计划结束日期：{proj.end_date.strftime('%Y-%m-%d')}",
                    new_content=f"申请延期至：{(proj.end_date + timedelta(days=30)).strftime('%Y-%m-%d')}",
                    applicant_id=leader.id,
                    status=random.choice([2, 3, 3]),
                    submit_time=proj.approval_time + timedelta(days=random.randint(40, 80)) if proj.approval_time else None,
                    approval_time=proj.approval_time + timedelta(days=random.randint(45, 85)) if proj.approval_time else None,
                )
                db.add(cr)

        db.commit()
        print("  -> 成果、报销、中期检查、变更申请创建完成")

        # ==================== 统计 ====================
        print("[6/6] 数据统计...")
        counts = {
            "项目": db.query(ProjProject).count(),
            "团队成员": db.query(ProjTeamMember).count(),
            "预算记录": db.query(ProjBudget).count(),
            "审核记录": db.query(ProjReview).count(),
            "成果": db.query(ProjAchievement).count(),
            "报销单": db.query(ProjExpense).count(),
            "中期检查": db.query(ProjMidtermCheck).count(),
            "变更申请": db.query(ProjChangeRequest).count(),
            "竞赛": db.query(Competition).count(),
        }
        for k, v in counts.items():
            print(f"  {k}: {v}")

        print("\n" + "=" * 60)
        print("  数据种子填充完成！")
        print("=" * 60)

    except Exception as e:
        db.rollback()
        print(f"[ERROR] 种子数据生成失败: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
