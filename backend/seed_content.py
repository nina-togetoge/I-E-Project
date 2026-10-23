"""
内容类种子数据规范化脚本（可重复执行）

覆盖范围：
  1. 公告：清空旧数据后重新生成面向真实业务场景的公告
  2. 大赛：规范联系方式、官网、届次与状态（保留已有 ID，不影响项目关联）
  3. 站内通知：清空旧数据后按演示账号的实际项目状态生成通知
  4. 演示项目文案：统一专家评分/评语、中期评语、成果编号与成果认定意见

运行方式（在 backend 目录下）：
  python seed_content.py
"""
import os
import sys
from datetime import datetime, date
from decimal import Decimal

_PROJ_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _PROJ_ROOT)

from sqlalchemy import text
from app.database.session import SessionLocal
from app.models import (
    Announcement, SysNotification, Competition, SysUser,
    ProjReview, ProjMidtermCheck, ProjAchievement, ProjAchievementReview,
)


# ================================================================
# 1. 公告
# ================================================================
ANNOUNCEMENTS = [
    {
        "title": "关于2026年校级大学生创新创业训练计划项目立项名单的公示",
        "announcement_type": 3, "status": 1, "priority": 2,
        "publish_time": datetime(2026, 10, 8, 10, 0),
        "expire_time": datetime(2026, 11, 8, 23, 59),
        "view_count": 326,
        "content": (
            "<p>各学院、各项目团队：</p>"
            "<p>根据《哈尔滨信息工程学院大学生创新创业训练计划项目管理办法》有关规定，"
            "经学生申报、指导教师确认、学院初审、校级复审和专家评审，2026年度校级大学生创新创业训练计划"
            "共立项创新训练项目28项、创业训练项目11项、创业实践项目6项，现予以公示。</p>"
            "<p>公示期为2026年10月8日至10月15日。公示期内如有异议，请以书面形式实名向创新创业学院反映，"
            "并提供必要的证明材料，逾期不再受理。</p>"
            "<p>联系人：王老师　联系电话：0451-8812 3456　电子邮箱：cxcy@hrbci.edu.cn</p>"
            "<p>办公地点：行政楼302室</p>"
            "<p style=\"text-align:right\">创新创业学院<br/>2026年10月8日</p>"
        ),
    },
    {
        "title": "关于做好2026年秋季学期大学生创新创业训练计划项目中期检查工作的通知",
        "announcement_type": 2, "status": 1, "priority": 2,
        "publish_time": datetime(2026, 9, 20, 9, 0),
        "expire_time": datetime(2026, 11, 30, 23, 59),
        "view_count": 214,
        "content": (
            "<p>各学院、各项目负责人：</p>"
            "<p>为加强项目过程管理，督促项目按计划推进，现启动2026年秋季学期中期检查工作，"
            "有关事项通知如下：</p>"
            "<p>一、检查范围：2026年度已立项且尚未通过中期检查的各级大学生创新创业训练计划项目。</p>"
            "<p>二、提交材料：项目进展情况、已完成任务、存在问题及下一步计划、经费使用情况。</p>"
            "<p>三、提交方式：项目负责人登录管理平台，在「中期检查」页面填写并提交，"
            "由指导教师审核。</p>"
            "<p>四、时间安排：学生提交截止2026年11月15日，指导教师审核截止2026年11月20日。</p>"
            "<p>五、未按期提交且未说明原因的项目，按自动终止处理，并收回已拨付经费。</p>"
            "<p style=\"text-align:right\">创新创业学院<br/>2026年9月20日</p>"
        ),
    },
    {
        "title": "关于2026年度大学生创新创业训练计划项目结题验收工作的通知",
        "announcement_type": 2, "status": 1, "priority": 2,
        "publish_time": datetime(2026, 10, 15, 9, 30),
        "expire_time": datetime(2026, 12, 31, 23, 59),
        "view_count": 167,
        "content": (
            "<p>各学院、各项目团队：</p>"
            "<p>2026年度大学生创新创业训练计划项目结题验收工作即将开始，现将有关要求通知如下：</p>"
            "<p>一、验收范围：已通过中期检查、达到结题条件的项目。</p>"
            "<p>二、提交材料：结项验收报告、项目成果清单及证明材料、经费决算说明。</p>"
            "<p>三、提交方式：项目负责人在平台「结项验收」页面提交，系统将自动校验中期检查结果、"
            "成果登记数量与经费结清情况。</p>"
            "<p>四、时间安排：报告提交截止2026年12月10日；结题答辩安排在12月中下旬，具体分组另行通知。</p>"
            "<p>五、每个项目由不少于两名评审专家独立验收，验收结论以多数意见为准。</p>"
            "<p style=\"text-align:right\">创新创业学院<br/>2026年10月15日</p>"
        ),
    },
    {
        "title": "第十三届中国国际大学生创新大赛校内选拔赛报名通知",
        "announcement_type": 2, "status": 1, "priority": 3,
        "publish_time": datetime(2026, 9, 5, 8, 30),
        "expire_time": datetime(2026, 11, 15, 23, 59),
        "view_count": 452,
        "content": (
            "<p>各学院：</p>"
            "<p>第十三届中国国际大学生创新大赛已启动，学校将组织校内选拔赛，择优推荐参加省赛。"
            "现将报名事项通知如下：</p>"
            "<p>一、赛道设置：高教主赛道、「青年红色筑梦之旅」赛道、产业命题赛道。</p>"
            "<p>二、参赛对象：全日制在校本科生、研究生及毕业五年内校友，以团队形式参赛，"
            "每个团队3至5人，须配备1至2名指导教师。</p>"
            "<p>三、报名方式：登录创新创业项目管理平台，选择本赛事完成项目申报，"
            "并上传商业计划书及支撑材料。</p>"
            "<p>四、时间安排：校内报名截止2026年10月31日；校内初赛10月下旬；"
            "省赛推荐名单于11月上旬公布。</p>"
            "<p>五、联系方式：创新创业学院竞赛办公室，电话0451-8812 3789。</p>"
            "<p style=\"text-align:right\">创新创业学院<br/>2026年9月5日</p>"
        ),
    },
    {
        "title": "关于规范项目经费报销流程的通知",
        "announcement_type": 1, "status": 1, "priority": 2,
        "publish_time": datetime(2026, 9, 25, 14, 0),
        "expire_time": None,
        "view_count": 198,
        "content": (
            "<p>各项目负责人、指导教师：</p>"
            "<p>为进一步规范创新创业项目经费使用，提高报销效率，现就报销流程明确如下：</p>"
            "<p>一、报销范围：设备费、材料费、差旅费、测试化验加工费、出版/文献/信息传播费等"
            "与项目研究直接相关的支出。</p>"
            "<p>二、报销要求：单笔支出须取得合法有效发票，发票抬头为学校全称；"
            "差旅费须附审批单和行程凭证；单笔金额超过5000元的须提前报备。</p>"
            "<p>三、审批流程：项目负责人在平台提交报销申请，经指导教师审核、学院管理员审核后，"
            "由财务处终审并办理支付。</p>"
            "<p>四、注意事项：报销金额不得超过项目预算及对应科目余额；"
            "已驳回的申请占用额度将自动释放，可修改后重新提交。</p>"
            "<p style=\"text-align:right\">财务处　创新创业学院<br/>2026年9月25日</p>"
        ),
    },
    {
        "title": "创新创业项目管理平台功能升级公告",
        "announcement_type": 1, "status": 1, "priority": 1,
        "publish_time": datetime(2026, 10, 18, 18, 0),
        "expire_time": None,
        "view_count": 271,
        "content": (
            "<p>各位师生：</p>"
            "<p>平台已于2026年10月18日完成版本升级，本次升级主要包括：</p>"
            "<p>1. 审核中心整合：待审核项目、变更申请、校级复审统一在「审核中心」按标签页处理；</p>"
            "<p>2. 结项工作台：成果登记与结项报告合并至同一页面，支持结项条件自动检查；</p>"
            "<p>3. 通知中心：审核结果、成果认定、结项验收等节点将通过站内信实时推送；</p>"
            "<p>4. 操作日志优化：仅记录新增、修改、删除、登录与导出行为，支持按模块和操作类型筛选。</p>"
            "<p>升级期间未对业务数据造成影响。如使用中遇到问题，请联系信息中心，电话0451-8812 3600。</p>"
            "<p style=\"text-align:right\">信息中心<br/>2026年10月18日</p>"
        ),
    },
    {
        "title": "创新创业项目管理平台学生端使用指南",
        "announcement_type": 4, "status": 1, "priority": 1,
        "publish_time": datetime(2026, 9, 10, 10, 0),
        "expire_time": None,
        "view_count": 583,
        "content": (
            "<p>各位同学：</p>"
            "<p>为帮助同学们快速熟悉平台操作，现将学生端主要流程说明如下：</p>"
            "<p>一、登录：使用学号作为账号登录，首次登录后请及时修改初始密码。</p>"
            "<p>二、项目申报：在「项目申报」页面填写项目名称、摘要、创新点、预期成果，"
            "选择参赛比赛、指导教师并添加团队成员，保存草稿后可继续修改。</p>"
            "<p>三、提交审核：材料齐备后提交，流程依次为指导教师确认、学院初审、校级复审、"
            "专家评审，可在项目详情页查看当前进度。</p>"
            "<p>四、过程管理：立项后按要求提交中期检查、登记项目成果、申请经费报销，"
            "达到结题条件后提交结项验收报告。</p>"
            "<p>五、常见问题：附件单个文件不超过200MB；项目被驳回后可在「我的项目」中修改并重新提交；"
            "同一比赛下每人只能参与一个项目。</p>"
            "<p style=\"text-align:right\">创新创业学院<br/>2026年9月10日</p>"
        ),
    },
    {
        "title": "关于举办2026年创新创业教育专题讲座的通知",
        "announcement_type": 4, "status": 1, "priority": 1,
        "publish_time": datetime(2026, 10, 20, 9, 0),
        "expire_time": datetime(2026, 10, 30, 23, 59),
        "view_count": 143,
        "content": (
            "<p>各学院：</p>"
            "<p>为提升学生创新创业项目选题与实施能力，学校特邀请省内高校创新创业教育专家开展专题讲座，"
            "具体安排如下：</p>"
            "<p>讲座主题：从创意到落地——大学生创新创业项目的选题与实施</p>"
            "<p>主讲人：哈尔滨工业大学创新创业教育中心 刘教授</p>"
            "<p>时间：2026年10月28日（星期三）14:00</p>"
            "<p>地点：图书馆报告厅</p>"
            "<p>参加人员：2026年立项项目团队成员、有意申报2027年项目的学生及指导教师。</p>"
            "<p>请各学院于10月26日前将参加人数报创新创业学院。</p>"
            "<p style=\"text-align:right\">创新创业学院<br/>2026年10月20日</p>"
        ),
    },
    {
        "title": "关于征集2027年大学生创新创业训练计划项目选题的通知",
        "announcement_type": 2, "status": 1, "priority": 1,
        "publish_time": datetime(2026, 10, 22, 15, 0),
        "expire_time": datetime(2026, 12, 20, 23, 59),
        "view_count": 96,
        "content": (
            "<p>各学院、各位教师：</p>"
            "<p>为做好2027年大学生创新创业训练计划项目储备，现面向全校征集项目选题，"
            "有关事项通知如下：</p>"
            "<p>一、征集方向：人工智能与智能制造、数字经济与乡村振兴、绿色低碳与生态环保、"
            "文化创意与社会服务等。</p>"
            "<p>二、选题要求：具有明确的创新点和应用场景，工作量与经费规模适合本科生团队"
            "在一年内完成，鼓励校企合作选题。</p>"
            "<p>三、提交方式：教师填写《项目选题征集表》，经所在学院汇总后于2026年11月30日前"
            "报送创新创业学院。</p>"
            "<p>四、入选选题将纳入2027年项目指南，面向全校学生发布并组织双向选择。</p>"
            "<p style=\"text-align:right\">创新创业学院<br/>2026年10月22日</p>"
        ),
    },
    {
        "title": "关于2026年大学生创新创业训练计划项目结题答辩安排的通知",
        "announcement_type": 2, "status": 1, "priority": 3,
        "publish_time": datetime(2026, 10, 22, 16, 0),
        "expire_time": datetime(2026, 12, 25, 23, 59),
        "view_count": 88,
        "content": (
            "<p>各项目团队：</p>"
            "<p>2026年度大学生创新创业训练计划项目结题答辩定于2026年12月20日举行，"
            "现将具体安排通知如下：</p>"
            "<p>一、答辩时间：2026年12月20日8:30—17:00。</p>"
            "<p>二、答辩地点：各学院分组进行，具体教室及分组名单于12月15日在平台公布。</p>"
            "<p>三、答辩形式：项目负责人汇报8分钟，专家提问5分钟；"
            "汇报内容包括项目完成情况、主要成果、经费使用和创新点。</p>"
            "<p>四、材料要求：请于12月10日前在平台提交结项验收报告，"
            "答辩当天携带成果证明材料原件备查。</p>"
            "<p>五、未按时提交材料或无故缺席答辩的项目，按结题不通过处理。</p>"
            "<p style=\"text-align:right\">创新创业学院<br/>2026年10月22日</p>"
        ),
    },
    {
        "title": "2026年暑期创新创业训练营报名通知",
        "announcement_type": 2, "status": 2, "priority": 1,
        "publish_time": datetime(2026, 6, 20, 10, 0),
        "expire_time": datetime(2026, 7, 15, 23, 59),
        "view_count": 364,
        "content": (
            "<p>各学院：</p>"
            "<p>学校将于2026年7月举办暑期创新创业训练营，围绕商业模式设计、"
            "产品原型开发、路演表达等模块开展集中培训，现面向全校学生开放报名。</p>"
            "<p>一、时间：2026年7月20日至7月26日。</p>"
            "<p>二、地点：大学生创新创业孵化基地。</p>"
            "<p>三、名额：80人，按报名顺序及项目基础择优录取。</p>"
            "<p>四、报名方式：登录平台「资源中心—活动报名」填写信息，报名截止7月15日。</p>"
            "<p>五、本次训练营已结束，相关课程资料可在资源中心下载。</p>"
            "<p style=\"text-align:right\">创新创业学院<br/>2026年6月20日</p>"
        ),
    },
    {
        "title": "2027年校级大学生创新创业训练计划项目预申报通知",
        "announcement_type": 2, "status": 0, "priority": 1,
        "publish_time": None,
        "expire_time": None,
        "view_count": 0,
        "content": (
            "<p>各学院：</p>"
            "<p>2027年校级大学生创新创业训练计划项目预申报工作拟于12月启动，"
            "具体申报条件、时间安排和材料要求待学校发文后另行通知。</p>"
            "<p>请各学院提前做好项目培育和团队组建工作。</p>"
            "<p style=\"text-align:right\">创新创业学院</p>"
        ),
    },
]


# ================================================================
# 2. 大赛规范化（按名称匹配，保留原 ID）
# ================================================================
COMPETITION_FIXES = {
    "第十三届中国国际大学生创新大赛": {
        "status": 2, "contact": "0451-8812 3789", "official_url": "https://cy.ncss.cn",
    },
    "第十八届挑战杯全国大学生课外学术科技作品竞赛": {
        "status": 2, "contact": "010-8521 2300", "official_url": "https://www.tiaozhanbei.net",
    },
    "2026年全国大学生数学建模竞赛": {
        "status": 3, "contact": "010-6278 1788", "official_url": "https://www.mcm.edu.cn",
    },
    "2026年校级大学生创新创业训练计划项目申报": {
        "status": 2, "contact": "0451-8812 3456", "official_url": "https://www.hrbci.edu.cn",
    },
    "第十届浙江省大学生创新创业大赛": {
        "status": 3, "contact": "0571-8795 1234", "official_url": "http://jyt.zj.gov.cn",
    },
    "中国创新创业大赛": {
        "status": 2, "contact": "010-8865 6789", "official_url": "https://www.cxcyds.com",
    },
    '"创青春"全国大学生创业大赛': {
        "status": 3, "contact": "010-6707 8899", "official_url": "http://www.chuangqingchun.net",
    },
    '全国大学生电子商务"创新、创意及创业"挑战赛': {
        "status": 2, "contact": "010-6228 5566", "official_url": "http://www.3chuang.net",
    },
    '"中国创翼"创业创新大赛': {
        "status": 2, "contact": "010-8422 6677", "official_url": "http://www.chinacxcy.cn",
    },
    "iCAN国际创新创业大赛": {
        "status": 2, "contact": "010-8264 7788", "official_url": None,
    },
    "全国大学生创新体验竞赛": {
        "status": 3, "contact": "025-8379 2200", "official_url": None,
    },
    "浙江省\"挑战杯\"大学生创业计划竞赛": {
        "status": 3, "contact": "0571-8705 3344", "official_url": None,
    },
}


# ================================================================
# 3. 演示项目文案规范化
# ================================================================
# (project_id, review_stage, reviewer_id) -> (score, dim_scores, comment)
EXPERT_REVIEW_FIXES = {
    (2, 3, 668): (
        Decimal("91.00"),
        {"创新性": 92, "可行性": 90, "团队": 89, "应用价值": 93},
        "项目聚焦校园垃圾分类场景，识别方案成熟，建议补充分类准确率的长期运行数据，同意立项。",
    ),
    (2, 3, 671): (
        Decimal("87.50"),
        {"创新性": 86, "可行性": 88, "团队": 86, "应用价值": 90},
        "系统架构清晰，硬件选型合理，终端部署成本偏高，建议优化后推广，同意立项。",
    ),
    (3, 3, 668): (
        Decimal("93.00"),
        {"创新性": 95, "可行性": 91, "团队": 92, "应用价值": 94},
        "知识图谱构建方法完整，推荐算法离线指标良好，创新性突出，建议优先支持。",
    ),
    (3, 3, 671): (
        Decimal("89.00"),
        {"创新性": 88, "可行性": 90, "团队": 88, "应用价值": 90},
        "选题具有应用价值，建议补充冷启动场景的实验验证，同意立项。",
    ),
    (4, 3, 668): (
        Decimal("92.00"),
        {"创新性": 91, "可行性": 93, "团队": 90, "应用价值": 94},
        "项目贴近校园实际需求，已形成可运行产品，技术路线清晰，同意立项。",
    ),
    (4, 3, 671): (
        Decimal("90.00"),
        {"创新性": 89, "可行性": 91, "团队": 89, "应用价值": 91},
        "小程序功能完整、迭代节奏合理，建议加强交易安全与信用约束机制，同意立项。",
    ),
}

# (project_id, review_stage) -> {reviewer_id: comment}
FINAL_REVIEW_FIXES = {
    (4, 4): {
        668: "结项材料齐全，系统运行稳定，已完成预期成果指标，同意结题。",
        671: "项目按计划完成全部任务，经费使用规范，成果证明材料完整，同意结题。",
    },
}

# (project_id, review_stage) -> comment（指导教师确认/学院初审/校级复审）
ROUTINE_REVIEW_FIXES = {
    (2, 0): "项目选题结合校园环保需求，技术路线清晰，同意提交学院审核。",
    (2, 1): "申报材料完整，经费预算合理，符合学院推荐条件，同意通过初审。",
    (2, 2): "项目方案可行，预期成果明确，同意通过校级复审并进入专家评审。",
    (3, 0): "项目围绕知识图谱技术开展学习资源推荐研究，专业契合度高，同意提交学院审核。",
    (3, 1): "团队配置合理，前期调研充分，同意通过学院初审。",
    (3, 2): "研究内容充实，技术路线可行，同意通过校级复审。",
    (4, 0): "项目面向校园二手交易场景，需求明确，同意提交学院审核。",
    (4, 1): "选题具有实用价值，预算编制规范，同意通过学院初审。",
    (4, 2): "项目已具备实施基础，同意通过校级复审。",
}

MIDTERM_COMMENT_FIXES = {
    3: "项目按计划完成知识图谱构建与推荐算法开发，阶段成果达到中期考核要求，同意通过中期检查。",
    4: "小程序已上线试运行，用户规模与功能完成度符合中期目标，经费使用合理，同意通过中期检查。",
}

# 成果编号规范化（按 项目ID + 成果标题 匹配）
ACHIEVEMENT_NO_FIXES = {
    (2, "校园智能垃圾分类回收系统 V1.0"): "2026SR0987654",
    (3, "课程知识图谱构建与推荐系统 V1.0"): "2026SR1023456",
    (3, "基于知识图谱的个性化学习资源推荐方法"): "10.19788/j.issn.1004-731X.2026.07.012",
    (4, "校园二手交易平台的设计与实现"): "10.19788/j.issn.1004-731X.2026.09.021",
}

ACHIEVEMENT_REVIEW_FIXES = {
    1: "软件著作权登记证书信息完整，与项目研究内容一致，予以认定。",
    2: "论文已正式发表，期刊信息与作者署名真实有效，予以认定。",
    3: "软件著作权登记材料齐全，权属清晰，予以认定。",
    4: "论文内容与项目研究方向一致，发表信息核验无误，予以认定。",
    5: "获奖证书真实有效，获奖等级与赛事信息一致，予以认定。",
}


# ================================================================
# 4. 站内通知
# ================================================================
NOTIFICATIONS = [
    {
        "username": "010101", "title": "项目申报草稿待提交",
        "content": "您创建的《基于Vue+FastAPI的校园创新创业项目管理平台》仍为草稿状态，请补充团队成员、预算明细等材料后提交指导教师确认。",
        "level": 1, "biz_type": "project", "biz_id": 1, "link": "/projects/1", "is_read": 0,
    },
    {
        "username": "010102", "title": "项目已获准立项",
        "content": "您负责的《面向校园的智能垃圾分类回收系统》已通过专家评审并正式立项，请按计划推进研究，并及时提交中期检查材料。",
        "level": 3, "biz_type": "project", "biz_id": 2, "link": "/projects/2", "is_read": 0,
    },
    {
        "username": "010103", "title": "结项验收报告待提交",
        "content": "您负责的《基于知识图谱的课程学习推荐平台》已通过中期检查，请于2026年12月10日前提交结项验收报告及相关成果材料。",
        "level": 2, "biz_type": "final", "biz_id": 3, "link": "/projects/3/final", "is_read": 0,
    },
    {
        "username": "010104", "title": "项目结题验收已通过",
        "content": "您负责的《校园二手交易小程序的设计与实现》结题验收已通过，项目正式结题，归档材料可在项目详情页导出。",
        "level": 3, "biz_type": "final", "biz_id": 4, "link": "/projects/4", "is_read": 1,
    },
    {
        "username": "01001", "title": "项目过程管理提醒",
        "content": "2026年秋季学期中期检查已启动，您指导的项目中尚有材料待完善，请在2026年11月20日前完成中期报告审核。",
        "level": 1, "biz_type": None, "biz_id": None, "link": "/review", "is_read": 0,
    },
    {
        "username": "00000", "title": "2026年度结题验收工作已启动",
        "content": "本年度结题验收工作已启动，请及时关注各学院材料提交进度，并在系统中完成结题验收审批。",
        "level": 1, "biz_type": None, "biz_id": None, "link": "/review", "is_read": 0,
    },
    {
        "username": "11111", "title": "学院初审待办提醒",
        "content": "您所在学院有项目处于待学院初审状态，请登录系统在「审核中心」及时处理。",
        "level": 2, "biz_type": None, "biz_id": None, "link": "/review", "is_read": 0,
    },
    {
        "username": "0101", "title": "结题验收评审已完成",
        "content": "您已完成《校园二手交易小程序的设计与实现》的结题验收评审，评审意见已归档。",
        "level": 3, "biz_type": "final", "biz_id": 4, "link": "/expert/pending", "is_read": 1,
    },
    {
        "username": "0201", "title": "结题验收评审已完成",
        "content": "您已完成《校园二手交易小程序的设计与实现》的结题验收评审，评审意见已归档。",
        "level": 3, "biz_type": "final", "biz_id": 4, "link": "/expert/pending", "is_read": 1,
    },
]


def seed():
    db = SessionLocal()
    try:
        # ---------- 公告 ----------
        db.query(Announcement).delete()
        db.commit()
        db.execute(text("ALTER TABLE biz_announcement AUTO_INCREMENT = 1"))
        db.commit()
        for item in ANNOUNCEMENTS:
            db.add(Announcement(
                title=item["title"],
                content=item["content"],
                announcement_type=item["announcement_type"],
                status=item["status"],
                priority=item["priority"],
                publish_time=item["publish_time"],
                expire_time=item["expire_time"],
                view_count=item["view_count"],
                created_by=1,
                created_at=item["publish_time"] or datetime.now(),
                is_deleted=0,
            ))
        db.commit()
        print(f"[公告] 已重新生成 {len(ANNOUNCEMENTS)} 条")

        # ---------- 大赛 ----------
        fixed = 0
        for comp in db.query(Competition).filter(Competition.is_deleted == 0).all():
            patch = COMPETITION_FIXES.get(comp.title)
            if not patch:
                continue
            for key, value in patch.items():
                setattr(comp, key, value)
            fixed += 1
        db.commit()
        print(f"[大赛] 已规范化 {fixed} 条")

        # ---------- 专家评审 ----------
        expert_fixed = 0
        for (pid, stage, rid), (score, dims, comment) in EXPERT_REVIEW_FIXES.items():
            rows = db.query(ProjReview).filter(
                ProjReview.project_id == pid,
                ProjReview.review_stage == stage,
                ProjReview.reviewer_id == rid,
                ProjReview.review_result == 1,
                ProjReview.is_deleted == 0,
            ).all()
            for row in rows:
                row.score = score
                row.dim_scores = dims
                row.review_comment = comment
                expert_fixed += 1

        # ---------- 结题验收 ----------
        for (pid, stage), comments in FINAL_REVIEW_FIXES.items():
            for rid, comment in comments.items():
                rows = db.query(ProjReview).filter(
                    ProjReview.project_id == pid,
                    ProjReview.review_stage == stage,
                    ProjReview.reviewer_id == rid,
                    ProjReview.review_result == 1,
                    ProjReview.is_deleted == 0,
                ).all()
                for row in rows:
                    row.review_comment = comment
                    expert_fixed += 1

        # ---------- 常规审核意见 ----------
        for (pid, stage), comment in ROUTINE_REVIEW_FIXES.items():
            rows = db.query(ProjReview).filter(
                ProjReview.project_id == pid,
                ProjReview.review_stage == stage,
                ProjReview.is_deleted == 0,
            ).all()
            for row in rows:
                row.review_comment = comment
        db.commit()
        print(f"[审核记录] 已更新 {expert_fixed} 条专家/结题意见，常规意见 {len(ROUTINE_REVIEW_FIXES)} 条")

        # ---------- 中期评语 ----------
        for midterm_id, comment in MIDTERM_COMMENT_FIXES.items():
            row = db.query(ProjMidtermCheck).filter(
                ProjMidtermCheck.id == midterm_id,
                ProjMidtermCheck.is_deleted == 0,
            ).first()
            if row:
                row.review_comment = comment
        db.commit()
        print(f"[中期检查] 已更新 {len(MIDTERM_COMMENT_FIXES)} 条评语")

        # ---------- 成果编号 ----------
        ach_fixed = 0
        for (pid, title), no in ACHIEVEMENT_NO_FIXES.items():
            rows = db.query(ProjAchievement).filter(
                ProjAchievement.project_id == pid,
                ProjAchievement.title == title,
                ProjAchievement.is_deleted == 0,
            ).all()
            for row in rows:
                row.achievement_no = no
                ach_fixed += 1
        db.commit()
        print(f"[成果] 已更新 {ach_fixed} 条成果编号")

        # ---------- 成果认定意见 ----------
        ar_fixed = 0
        for achievement_id, comment in ACHIEVEMENT_REVIEW_FIXES.items():
            rows = db.query(ProjAchievementReview).filter(
                ProjAchievementReview.achievement_id == achievement_id,
                ProjAchievementReview.is_deleted == 0,
            ).all()
            for row in rows:
                row.review_comment = comment
                ar_fixed += 1
        db.commit()
        print(f"[成果认定] 已更新 {ar_fixed} 条认定意见")

        # ---------- 站内通知 ----------
        db.query(SysNotification).delete()
        db.commit()
        db.execute(text("ALTER TABLE sys_notification AUTO_INCREMENT = 1"))
        db.commit()
        created = 0
        now = datetime.now()
        for item in NOTIFICATIONS:
            user = db.query(SysUser).filter(SysUser.username == item["username"]).first()
            if not user:
                print(f"  ! 通知跳过：账号 {item['username']} 不存在")
                continue
            db.add(SysNotification(
                user_id=user.id,
                title=item["title"],
                content=item["content"],
                level=item["level"],
                biz_type=item["biz_type"],
                biz_id=item["biz_id"],
                link=item["link"],
                is_read=item["is_read"],
                read_time=now if item["is_read"] else None,
            ))
            created += 1
        db.commit()
        print(f"[通知] 已生成 {created} 条")

        print("内容类种子数据规范化完成")
    except Exception as exc:
        db.rollback()
        print(f"[ERROR] {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
