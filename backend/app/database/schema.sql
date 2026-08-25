-- ====================================================================
-- 校园创新创业项目管理平台 数据库建表脚本
-- 数据库版本: MySQL 8.0+
-- 字符集: utf8mb4
-- 创建日期: 2024
-- ====================================================================

-- 创建数据库
CREATE DATABASE IF NOT EXISTS ie_project_db
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE ie_project_db;

-- ====================================================================
-- 1. 系统用户表 (sys_user)
-- ====================================================================
DROP TABLE IF EXISTS sys_user;
CREATE TABLE sys_user (
    id              BIGINT          NOT NULL AUTO_INCREMENT              COMMENT '用户ID',
    username        VARCHAR(64)     NOT NULL                             COMMENT '登录账号(学号/工号)',
    password_hash   VARCHAR(255)    NOT NULL                             COMMENT '密码哈希',
    real_name       VARCHAR(64)     NOT NULL                             COMMENT '真实姓名',
    email           VARCHAR(128)    DEFAULT NULL                         COMMENT '邮箱',
    phone           VARCHAR(20)     DEFAULT NULL                         COMMENT '手机号',
    role            TINYINT         NOT NULL DEFAULT 1                   COMMENT '角色: 1-学生 2-指导教师 3-评审专家 4-系统管理员',
    college_id      BIGINT          DEFAULT NULL                         COMMENT '所属学院ID',
    avatar          VARCHAR(255)    DEFAULT NULL                         COMMENT '头像URL',
    status          TINYINT         NOT NULL DEFAULT 1                   COMMENT '状态: 0-禁用 1-启用',
    force_change_pwd TINYINT        NOT NULL DEFAULT 0                   COMMENT '首次登录强制改密: 0-否 1-是',
    last_login_at   DATETIME        DEFAULT NULL                         COMMENT '最后登录时间',
    last_login_ip   VARCHAR(64)     DEFAULT NULL                         COMMENT '最后登录IP',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP    COMMENT '创建时间',
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    is_deleted      TINYINT         NOT NULL DEFAULT 0                   COMMENT '软删除标记: 0-未删除 1-已删除',
    PRIMARY KEY (id),
    UNIQUE KEY uk_username (username),
    KEY idx_college (college_id),
    KEY idx_role (role),
    KEY idx_status (status),
    KEY idx_email (email),
    KEY idx_phone (phone)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='系统用户表';

-- ====================================================================
-- 2. 学院表 (sys_college)
-- ====================================================================
DROP TABLE IF EXISTS sys_college;
CREATE TABLE sys_college (
    id              BIGINT          NOT NULL AUTO_INCREMENT              COMMENT '学院ID',
    college_code    VARCHAR(32)     NOT NULL                             COMMENT '学院编码',
    college_name    VARCHAR(128)    NOT NULL                             COMMENT '学院名称',
    dean_id         BIGINT          DEFAULT NULL                         COMMENT '院长用户ID',
    sort_order      INT             NOT NULL DEFAULT 0                   COMMENT '排序',
    status          TINYINT         NOT NULL DEFAULT 1                   COMMENT '状态: 0-停用 1-启用',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP    COMMENT '创建时间',
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_college_code (college_code),
    UNIQUE KEY uk_college_name (college_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='学院表';

-- ====================================================================
-- 3. 项目表 (proj_project)
-- ====================================================================
DROP TABLE IF EXISTS proj_project;
CREATE TABLE proj_project (
    id                  BIGINT          NOT NULL AUTO_INCREMENT              COMMENT '项目ID',
    project_no          VARCHAR(64)     DEFAULT NULL                         COMMENT '项目编号',
    project_name        VARCHAR(255)    NOT NULL                             COMMENT '项目名称',
    project_type        TINYINT         NOT NULL DEFAULT 1                   COMMENT '项目类型: 1-创新训练 2-创业训练 3-创业实践',
    project_level       TINYINT         NOT NULL DEFAULT 1                   COMMENT '项目级别: 1-校级 2-省级 3-国家级',
    college_id          BIGINT          NOT NULL                             COMMENT '申报学院ID',
    leader_id           BIGINT          NOT NULL                             COMMENT '项目负责人(学生)ID',
    teacher_id          BIGINT          DEFAULT NULL                         COMMENT '指导教师ID',
    start_date          DATE            DEFAULT NULL                         COMMENT '立项开始日期',
    end_date            DATE            DEFAULT NULL                         COMMENT '计划结束日期',
    budget_amount       DECIMAL(12,2)   NOT NULL DEFAULT 0.00                COMMENT '预算总额(元)',
    used_amount         DECIMAL(12,2)   NOT NULL DEFAULT 0.00                COMMENT '已使用金额(元)',
    project_summary     TEXT            DEFAULT NULL                         COMMENT '项目简介',
    innovation_points   TEXT            DEFAULT NULL                         COMMENT '创新点',
    expected_results    TEXT            DEFAULT NULL                         COMMENT '预期成果',
    status              TINYINT         NOT NULL DEFAULT 0                   COMMENT '项目状态: 0-草稿 1-待学院初审 2-学院初审通过 3-待校级复审 4-校级复审通过 5-待专家评审 6-已立项 7-中期检查 8-待结题 9-已结题 10-已驳回 11-已撤销',
    submit_time         DATETIME        DEFAULT NULL                         COMMENT '正式提交时间',
    approval_time       DATETIME        DEFAULT NULL                         COMMENT '最终立项审批时间',
    current_approver_id BIGINT          DEFAULT NULL                         COMMENT '当前审批人ID',
    reject_reason       VARCHAR(500)    DEFAULT NULL                         COMMENT '驳回原因',
    created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP    COMMENT '创建时间',
    updated_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    is_deleted          TINYINT         NOT NULL DEFAULT 0                   COMMENT '软删除标记',
    PRIMARY KEY (id),
    UNIQUE KEY uk_project_no (project_no),
    KEY idx_college (college_id),
    KEY idx_leader (leader_id),
    KEY idx_teacher (teacher_id),
    KEY idx_status (status),
    KEY idx_type_level (project_type, project_level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='创新创业项目表';

-- ====================================================================
-- 4. 项目团队成员表 (proj_team_member)
-- ====================================================================
DROP TABLE IF EXISTS proj_team_member;
CREATE TABLE proj_team_member (
    id              BIGINT          NOT NULL AUTO_INCREMENT              COMMENT '记录ID',
    project_id      BIGINT          NOT NULL                             COMMENT '项目ID',
    student_id      BIGINT          NOT NULL                             COMMENT '学生用户ID',
    student_name    VARCHAR(64)     NOT NULL                             COMMENT '学生姓名(冗余)',
    student_no      VARCHAR(64)     NOT NULL                             COMMENT '学号(冗余)',
    major           VARCHAR(128)    DEFAULT NULL                         COMMENT '专业',
    grade           VARCHAR(32)     DEFAULT NULL                         COMMENT '年级',
    role_in_team    VARCHAR(64)     DEFAULT NULL                         COMMENT '团队内角色',
    task_desc       VARCHAR(255)    DEFAULT NULL                         COMMENT '分工描述',
    join_time       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP    COMMENT '加入时间',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP    COMMENT '创建时间',
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    is_deleted      TINYINT         NOT NULL DEFAULT 0                   COMMENT '软删除标记',
    PRIMARY KEY (id),
    UNIQUE KEY uk_project_student (project_id, student_id),
    KEY idx_student (student_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='项目团队成员表';

-- ====================================================================
-- 5. 项目审核记录表 (proj_review)
-- ====================================================================
DROP TABLE IF EXISTS proj_review;
CREATE TABLE proj_review (
    id              BIGINT          NOT NULL AUTO_INCREMENT              COMMENT '记录ID',
    project_id      BIGINT          NOT NULL                             COMMENT '项目ID',
    review_stage    TINYINT         NOT NULL                             COMMENT '审核阶段: 1-学院初审 2-校级复审 3-专家评审 4-结题验收',
    reviewer_id     BIGINT          NOT NULL                             COMMENT '审核人ID',
    reviewer_name   VARCHAR(64)     NOT NULL                             COMMENT '审核人姓名(冗余)',
    review_result   TINYINT         NOT NULL                             COMMENT '审核结果: 1-通过 2-驳回 3-修改后重提 99-待评审(占位)',
    score           DECIMAL(5,2)    DEFAULT NULL                         COMMENT '评分(百分制,专家评审用)',
    review_comment  VARCHAR(1000)   DEFAULT NULL                         COMMENT '评审意见',
    review_time     DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP    COMMENT '审核时间',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP    COMMENT '创建时间',
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    is_deleted      TINYINT         NOT NULL DEFAULT 0                   COMMENT '软删除标记',
    PRIMARY KEY (id),
    KEY idx_project (project_id),
    KEY idx_reviewer (reviewer_id),
    KEY idx_stage (review_stage),
    KEY idx_project_stage (project_id, review_stage),
    CONSTRAINT chk_review_result CHECK (review_result IN (1,2,3,99))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='项目审核记录表';

-- ====================================================================
-- 6. 项目预算表 (proj_budget)
-- ====================================================================
DROP TABLE IF EXISTS proj_budget;
CREATE TABLE proj_budget (
    id              BIGINT          NOT NULL AUTO_INCREMENT              COMMENT '记录ID',
    project_id      BIGINT          NOT NULL                             COMMENT '项目ID',
    budget_item     VARCHAR(128)    NOT NULL                             COMMENT '预算科目',
    budget_amount   DECIMAL(12,2)   NOT NULL DEFAULT 0.00                COMMENT '预算金额',
    used_amount     DECIMAL(12,2)   NOT NULL DEFAULT 0.00                COMMENT '已使用金额',
    remark          VARCHAR(255)    DEFAULT NULL                         COMMENT '备注说明',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP    COMMENT '创建时间',
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    is_deleted      TINYINT         NOT NULL DEFAULT 0                   COMMENT '软删除标记',
    PRIMARY KEY (id),
    KEY idx_project (project_id),
    KEY idx_project_budget_item (project_id, budget_item)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='项目预算表';

-- ====================================================================
-- 7. 经费报销申请表 (proj_expense)
-- ====================================================================
DROP TABLE IF EXISTS proj_expense;
CREATE TABLE proj_expense (
    id              BIGINT          NOT NULL AUTO_INCREMENT              COMMENT '报销单ID',
    expense_no      VARCHAR(64)     NOT NULL                             COMMENT '报销单号',
    project_id      BIGINT          NOT NULL                             COMMENT '项目ID',
    applicant_id    BIGINT          NOT NULL                             COMMENT '申请人ID',
    applicant_name  VARCHAR(64)     NOT NULL                             COMMENT '申请人姓名(冗余)',
    expense_amount  DECIMAL(12,2)   NOT NULL                             COMMENT '报销金额',
    budget_item_id  BIGINT          DEFAULT NULL                         COMMENT '对应预算科目ID',
    expense_desc    VARCHAR(500)    NOT NULL                             COMMENT '费用说明',
    invoice_no      VARCHAR(128)    DEFAULT NULL                         COMMENT '发票号码',
    status          TINYINT         NOT NULL DEFAULT 0                   COMMENT '审批状态: 0-草稿 1-待导师审批 2-导师审批通过 3-待学院审批 4-学院审批通过 5-待财务审批 6-已完成 7-已驳回',
    reject_reason   VARCHAR(500)    DEFAULT NULL                         COMMENT '驳回原因',
    submit_time     DATETIME        DEFAULT NULL                         COMMENT '提交时间',
    approval_time   DATETIME        DEFAULT NULL                         COMMENT '最终审批时间',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP    COMMENT '创建时间',
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    is_deleted      TINYINT         NOT NULL DEFAULT 0                   COMMENT '软删除标记',
    PRIMARY KEY (id),
    UNIQUE KEY uk_expense_no (expense_no),
    KEY idx_project (project_id),
    KEY idx_applicant (applicant_id),
    KEY idx_status (status),
    KEY idx_created_at (created_at),
    KEY idx_budget_item (budget_item_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='经费报销申请表';

-- ====================================================================
-- 8. 项目成果表 (proj_achievement)
-- ====================================================================
DROP TABLE IF EXISTS proj_achievement;
CREATE TABLE proj_achievement (
    id              BIGINT          NOT NULL AUTO_INCREMENT              COMMENT '成果ID',
    project_id      BIGINT          NOT NULL                             COMMENT '项目ID',
    achievement_type TINYINT        NOT NULL                             COMMENT '成果类型: 1-论文 2-专利 3-软件著作权 4-竞赛获奖 5-创业成果 6-其他',
    title           VARCHAR(255)    NOT NULL                             COMMENT '成果标题/名称',
    author          VARCHAR(255)    DEFAULT NULL                         COMMENT '作者/发明人',
    publish_date    DATE            DEFAULT NULL                         COMMENT '发表/授权日期',
    publisher       VARCHAR(255)    DEFAULT NULL                         COMMENT '发表刊物/授权机构',
    achievement_no  VARCHAR(128)    DEFAULT NULL                         COMMENT '编号(专利号/登记号等)',
    level           TINYINT         DEFAULT NULL                         COMMENT '级别: 1-校级 2-省级 3-国家级 4-国际级',
    award_level     VARCHAR(64)     DEFAULT NULL                         COMMENT '获奖等级',
    summary         TEXT            DEFAULT NULL                         COMMENT '成果简介',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP    COMMENT '创建时间',
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    is_deleted      TINYINT         NOT NULL DEFAULT 0                   COMMENT '软删除标记',
    PRIMARY KEY (id),
    KEY idx_project (project_id),
    KEY idx_type (achievement_type),
    KEY idx_achievement_no (achievement_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='项目成果表';

-- ====================================================================
-- 9. 附件文件表 (sys_attachment)
-- ====================================================================
DROP TABLE IF EXISTS sys_attachment;
CREATE TABLE sys_attachment (
    id              BIGINT          NOT NULL AUTO_INCREMENT              COMMENT '附件ID',
    biz_type        VARCHAR(64)     NOT NULL                             COMMENT '业务类型: project-项目材料 expense-报销附件 achievement-成果材料 review-评审材料',
    biz_id          BIGINT          NOT NULL                             COMMENT '业务记录ID',
    file_name       VARCHAR(255)    NOT NULL                             COMMENT '原始文件名',
    file_path       VARCHAR(500)    NOT NULL                             COMMENT '存储路径',
    file_size       BIGINT          NOT NULL                             COMMENT '文件大小(字节)',
    file_type       VARCHAR(255)    DEFAULT NULL                         COMMENT '文件MIME类型',
    file_ext        VARCHAR(16)     DEFAULT NULL                         COMMENT '文件扩展名',
    uploader_id     BIGINT          NOT NULL                             COMMENT '上传人ID',
    uploader_name   VARCHAR(64)     NOT NULL                             COMMENT '上传人姓名(冗余)',
    download_count  INT             NOT NULL DEFAULT 0                   COMMENT '下载次数',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP    COMMENT '上传时间',
    is_deleted      TINYINT         NOT NULL DEFAULT 0                   COMMENT '软删除标记',
    PRIMARY KEY (id),
    KEY idx_biz (biz_type, biz_id),
    KEY idx_uploader (uploader_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='附件文件表';

-- ====================================================================
-- 10. 操作日志表 (sys_operation_log)
-- ====================================================================
DROP TABLE IF EXISTS sys_operation_log;
CREATE TABLE sys_operation_log (
    id              BIGINT          NOT NULL AUTO_INCREMENT              COMMENT '日志ID',
    user_id         BIGINT          DEFAULT NULL                         COMMENT '操作用户ID',
    username        VARCHAR(64)     DEFAULT NULL                         COMMENT '操作账号',
    real_name       VARCHAR(64)     DEFAULT NULL                         COMMENT '操作人姓名',
    user_role       TINYINT         DEFAULT NULL                         COMMENT '用户角色',
    operation_type  VARCHAR(64)     NOT NULL                             COMMENT '操作类型: create/update/delete/login/export/approve等',
    module_name     VARCHAR(64)     NOT NULL                             COMMENT '模块名称',
    operation_desc  VARCHAR(500)    DEFAULT NULL                         COMMENT '操作描述',
    request_method  VARCHAR(16)     DEFAULT NULL                         COMMENT '请求方法',
    request_url     VARCHAR(500)    DEFAULT NULL                         COMMENT '请求URL',
    request_params  TEXT            DEFAULT NULL                         COMMENT '请求参数(JSON)',
    response_code   INT             DEFAULT NULL                         COMMENT '响应状态码',
    ip_address      VARCHAR(64)     DEFAULT NULL                         COMMENT '操作IP',
    user_agent      VARCHAR(500)    DEFAULT NULL                         COMMENT '客户端UA',
    cost_time       INT             DEFAULT NULL                         COMMENT '耗时(毫秒)',
    operation_time  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP    COMMENT '操作时间',
    PRIMARY KEY (id),
    KEY idx_user (user_id),
    KEY idx_username (username),
    KEY idx_operation (operation_type, module_name),
    KEY idx_time (operation_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='操作日志审计表';

-- ====================================================================
-- 11. 中期检查表 (proj_midterm_check)
-- ====================================================================
DROP TABLE IF EXISTS proj_midterm_check;
CREATE TABLE proj_midterm_check (
    id              BIGINT          NOT NULL AUTO_INCREMENT              COMMENT '记录ID',
    project_id      BIGINT          NOT NULL                             COMMENT '项目ID',
    progress_desc   TEXT            DEFAULT NULL                         COMMENT '当前进展描述',
    completed_tasks TEXT            DEFAULT NULL                         COMMENT '已完成任务',
    remaining_tasks TEXT            DEFAULT NULL                         COMMENT '剩余任务计划',
    problems        TEXT            DEFAULT NULL                         COMMENT '存在问题',
    next_plan       TEXT            DEFAULT NULL                         COMMENT '下一步计划',
    budget_usage    DECIMAL(12,2)   DEFAULT NULL                         COMMENT '已使用经费',
    status          TINYINT         NOT NULL DEFAULT 0                   COMMENT '状态: 0-草稿 1-待审核 2-审核通过 3-需修改 4-已驳回',
    reviewer_id     BIGINT          DEFAULT NULL                         COMMENT '审核人ID',
    review_comment  VARCHAR(1000)   DEFAULT NULL                         COMMENT '审核意见',
    review_time     DATETIME        DEFAULT NULL                         COMMENT '审核时间',
    submit_time     DATETIME        DEFAULT NULL                         COMMENT '提交时间',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP    COMMENT '创建时间',
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_project (project_id),
    KEY idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='项目中期检查表';

-- ====================================================================
-- 12. 项目变更/延期申请表 (proj_change_request)
-- ====================================================================
DROP TABLE IF EXISTS proj_change_request;
CREATE TABLE proj_change_request (
    id              BIGINT          NOT NULL AUTO_INCREMENT              COMMENT '申请ID',
    project_id      BIGINT          NOT NULL                             COMMENT '项目ID',
    change_type     TINYINT         NOT NULL                             COMMENT '变更类型: 1-延期 2-人员变更 3-内容变更 4-预算调整 5-其他',
    change_reason   VARCHAR(1000)   NOT NULL                             COMMENT '变更原因',
    original_content TEXT           DEFAULT NULL                         COMMENT '原内容',
    new_content     TEXT            DEFAULT NULL                         COMMENT '变更后内容',
    applicant_id    BIGINT          NOT NULL                             COMMENT '申请人ID',
    status          TINYINT         NOT NULL DEFAULT 0                   COMMENT '状态: 0-待审核 1-导师同意 2-学院同意 3-校级同意 4-已驳回',
    reject_reason   VARCHAR(500)    DEFAULT NULL                         COMMENT '驳回原因',
    submit_time     DATETIME        DEFAULT NULL                         COMMENT '提交时间',
    approval_time   DATETIME        DEFAULT NULL                         COMMENT '审批时间',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP    COMMENT '创建时间',
    PRIMARY KEY (id),
    KEY idx_project (project_id),
    KEY idx_type_status (change_type, status),
    KEY idx_applicant (applicant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='项目变更/延期申请表';

-- ====================================================================
-- 13. 系统字典表 (sys_dict)
-- ====================================================================
DROP TABLE IF EXISTS sys_dict;
CREATE TABLE sys_dict (
    id              BIGINT          NOT NULL AUTO_INCREMENT              COMMENT '字典ID',
    dict_type       VARCHAR(64)     NOT NULL                             COMMENT '字典类型',
    dict_code       VARCHAR(64)     NOT NULL                             COMMENT '字典编码',
    dict_label      VARCHAR(255)    NOT NULL                             COMMENT '字典标签',
    dict_value      VARCHAR(255)    DEFAULT NULL                         COMMENT '字典值',
    sort_order      INT             NOT NULL DEFAULT 0                   COMMENT '排序',
    status          TINYINT         NOT NULL DEFAULT 1                   COMMENT '状态: 0-禁用 1-启用',
    remark          VARCHAR(500)    DEFAULT NULL                         COMMENT '备注',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP    COMMENT '创建时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_type_code (dict_type, dict_code),
    KEY idx_type (dict_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='系统字典表';

-- ====================================================================
-- 初始化数据
-- ====================================================================

-- 初始化学院数据
INSERT INTO sys_college (college_code, college_name, sort_order) VALUES
('CS', '计算机科学与技术学院', 1),
('SE', '软件工程学院', 2),
('EE', '电子信息工程学院', 3),
('ME', '机械工程学院', 4),
('BA', '经济管理学院', 5),
('AR', '艺术设计学院', 6);

-- 初始化管理员用户 (密码: admin123, 使用bcrypt加密)
INSERT INTO sys_user (username, password_hash, real_name, email, role, college_id, status) VALUES
('admin', '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW', '系统管理员', 'admin@university.edu.cn', 4, NULL, 1),
('student001', '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW', '张三', 'zhangsan@stu.edu.cn', 1, 2, 1),
('teacher001', '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW', '李教授', 'lisi@univ.edu.cn', 2, 2, 1),
('expert001', '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW', '王专家', 'wangwu@expert.com', 3, NULL, 1),
('college_admin', '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW', '学院管理员', 'ca@univ.edu.cn', 4, 2, 1);

-- 初始化系统字典
INSERT INTO sys_dict (dict_type, dict_code, dict_label, sort_order) VALUES
('user_role', '1', '学生', 1),
('user_role', '2', '指导教师', 2),
('user_role', '3', '评审专家', 3),
('user_role', '4', '系统管理员', 4),
('project_type', '1', '创新训练项目', 1),
('project_type', '2', '创业训练项目', 2),
('project_type', '3', '创业实践项目', 3),
('project_level', '1', '校级项目', 1),
('project_level', '2', '省级项目', 2),
('project_level', '3', '国家级项目', 3);

-- ====================================================================
-- 外键约束（所有表创建完成后追加，避免循环依赖/建表顺序问题）
--   ON DELETE 策略：
--     用户/学院删除 -> SET NULL（保留历史数据）
--     项目删除 -> CASCADE（子表随项目一起删）
-- ====================================================================

-- sys_user -> sys_college
ALTER TABLE sys_user ADD CONSTRAINT fk_user_college
    FOREIGN KEY (college_id) REFERENCES sys_college(id)
    ON DELETE SET NULL ON UPDATE CASCADE;

-- sys_college -> sys_user (dean)
ALTER TABLE sys_college ADD CONSTRAINT fk_college_dean
    FOREIGN KEY (dean_id) REFERENCES sys_user(id)
    ON DELETE SET NULL ON UPDATE CASCADE;

-- proj_project -> sys_user (leader/teacher)
ALTER TABLE proj_project ADD CONSTRAINT fk_project_leader
    FOREIGN KEY (leader_id) REFERENCES sys_user(id)
    ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE proj_project ADD CONSTRAINT fk_project_teacher
    FOREIGN KEY (teacher_id) REFERENCES sys_user(id)
    ON DELETE SET NULL ON UPDATE CASCADE;
-- proj_project -> sys_college
ALTER TABLE proj_project ADD CONSTRAINT fk_project_college
    FOREIGN KEY (college_id) REFERENCES sys_college(id)
    ON DELETE RESTRICT ON UPDATE CASCADE;

-- proj_team_member -> proj_project / sys_user
ALTER TABLE proj_team_member ADD CONSTRAINT fk_team_project
    FOREIGN KEY (project_id) REFERENCES proj_project(id)
    ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE proj_team_member ADD CONSTRAINT fk_team_student
    FOREIGN KEY (student_id) REFERENCES sys_user(id)
    ON DELETE RESTRICT ON UPDATE CASCADE;

-- proj_review -> proj_project / sys_user
ALTER TABLE proj_review ADD CONSTRAINT fk_review_project
    FOREIGN KEY (project_id) REFERENCES proj_project(id)
    ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE proj_review ADD CONSTRAINT fk_review_reviewer
    FOREIGN KEY (reviewer_id) REFERENCES sys_user(id)
    ON DELETE RESTRICT ON UPDATE CASCADE;

-- proj_budget -> proj_project
ALTER TABLE proj_budget ADD CONSTRAINT fk_budget_project
    FOREIGN KEY (project_id) REFERENCES proj_project(id)
    ON DELETE CASCADE ON UPDATE CASCADE;

-- proj_expense -> proj_project / sys_user / proj_budget
ALTER TABLE proj_expense ADD CONSTRAINT fk_expense_project
    FOREIGN KEY (project_id) REFERENCES proj_project(id)
    ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE proj_expense ADD CONSTRAINT fk_expense_applicant
    FOREIGN KEY (applicant_id) REFERENCES sys_user(id)
    ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE proj_expense ADD CONSTRAINT fk_expense_budget_item
    FOREIGN KEY (budget_item_id) REFERENCES proj_budget(id)
    ON DELETE SET NULL ON UPDATE CASCADE;

-- proj_achievement -> proj_project
ALTER TABLE proj_achievement ADD CONSTRAINT fk_achievement_project
    FOREIGN KEY (project_id) REFERENCES proj_project(id)
    ON DELETE CASCADE ON UPDATE CASCADE;

-- sys_attachment -> sys_user
ALTER TABLE sys_attachment ADD CONSTRAINT fk_attachment_uploader
    FOREIGN KEY (uploader_id) REFERENCES sys_user(id)
    ON DELETE RESTRICT ON UPDATE CASCADE;

-- proj_midterm_check -> proj_project / sys_user
ALTER TABLE proj_midterm_check ADD CONSTRAINT fk_midterm_project
    FOREIGN KEY (project_id) REFERENCES proj_project(id)
    ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE proj_midterm_check ADD CONSTRAINT fk_midterm_reviewer
    FOREIGN KEY (reviewer_id) REFERENCES sys_user(id)
    ON DELETE SET NULL ON UPDATE CASCADE;

-- proj_change_request -> proj_project / sys_user
ALTER TABLE proj_change_request ADD CONSTRAINT fk_change_project
    FOREIGN KEY (project_id) REFERENCES proj_project(id)
    ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE proj_change_request ADD CONSTRAINT fk_change_applicant
    FOREIGN KEY (applicant_id) REFERENCES sys_user(id)
    ON DELETE RESTRICT ON UPDATE CASCADE;

-- sys_operation_log -> sys_user (log留存历史，不级联删除)
ALTER TABLE sys_operation_log ADD CONSTRAINT fk_log_user
    FOREIGN KEY (user_id) REFERENCES sys_user(id)
    ON DELETE SET NULL ON UPDATE CASCADE;

