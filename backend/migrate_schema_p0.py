"""
P0/P1 生产数据库迁移脚本 (一次性执行)
运行方式:  cd backend ; python migrate_schema_p0.py
功能:
  1. 补 sys_user.force_change_pwd 列 (首次登录强制改密)
  2. 补 proj_team_member / proj_review / proj_budget 的 is_deleted、updated_at 列
  3. 新增若干二级索引 (created_at、username、achievement_no 等)
  4. 追加全部外键约束 (保证数据一致性)
  5. 删除 proj_team_member.idx_project 冗余索引 (UK 已覆盖)
安全: 所有 ADD COLUMN / ADD INDEX / ADD CONSTRAINT 均使用 IF NOT EXISTS 风格
      (MySQL 对 IF NOT EXISTS 支持不完整，这里用 try/except 吞掉重复创建的异常。)
"""
import traceback
from pathlib import Path
import sys

# 保证 app 包可导入
_BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(_BASE))
# IDE/原项目将依赖解包到 python_packages 目录，确保 sqlalchemy 等能被找到
_PKGS = _BASE / "python_packages"
if _PKGS.is_dir():
    sys.path.insert(0, str(_PKGS))

from sqlalchemy import text
from app.database.session import engine


DDL_STATEMENTS = [
    # ========= 1. 新增列 =========
    ("ADD COLUMN sys_user.force_change_pwd",
     "ALTER TABLE sys_user ADD COLUMN force_change_pwd TINYINT NOT NULL DEFAULT 0 COMMENT '首次登录强制改密' AFTER status"),

    ("ADD COLUMN proj_team_member.updated_at",
     "ALTER TABLE proj_team_member ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间' AFTER created_at"),
    ("ADD COLUMN proj_team_member.is_deleted",
     "ALTER TABLE proj_team_member ADD COLUMN is_deleted TINYINT NOT NULL DEFAULT 0 COMMENT '软删除标记' AFTER updated_at"),

    ("ADD COLUMN proj_review.updated_at",
     "ALTER TABLE proj_review ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间' AFTER created_at"),
    ("ADD COLUMN proj_review.is_deleted",
     "ALTER TABLE proj_review ADD COLUMN is_deleted TINYINT NOT NULL DEFAULT 0 COMMENT '软删除标记' AFTER updated_at"),

    ("ADD COLUMN proj_budget.is_deleted",
     "ALTER TABLE proj_budget ADD COLUMN is_deleted TINYINT NOT NULL DEFAULT 0 COMMENT '软删除标记' AFTER updated_at"),

    # ========= 2. 删除冗余索引 =========
    ("DROP REDUNDANT idx_project ON proj_team_member (UK 已覆盖 project_id,student_id)",
     "ALTER TABLE proj_team_member DROP INDEX idx_project"),

    # ========= 3. 新增二级索引 =========
    ("ADD idx_email sys_user",
     "ALTER TABLE sys_user ADD INDEX idx_email (email)"),
    ("ADD idx_phone sys_user",
     "ALTER TABLE sys_user ADD INDEX idx_phone (phone)"),

    ("ADD idx_created_at proj_expense",
     "ALTER TABLE proj_expense ADD INDEX idx_created_at (created_at)"),
    ("ADD idx_budget_item proj_expense",
     "ALTER TABLE proj_expense ADD INDEX idx_budget_item (budget_item_id)"),

    ("ADD idx_achievement_no proj_achievement",
     "ALTER TABLE proj_achievement ADD INDEX idx_achievement_no (achievement_no)"),

    ("ADD idx_username sys_operation_log",
     "ALTER TABLE sys_operation_log ADD INDEX idx_username (username)"),

    ("ADD idx_applicant proj_change_request",
     "ALTER TABLE proj_change_request ADD INDEX idx_applicant (applicant_id)"),

    ("ADD idx_project_budget_item proj_budget",
     "ALTER TABLE proj_budget ADD INDEX idx_project_budget_item (project_id, budget_item)"),

    # ========= 4. 外键约束 =========
    # sys_user / sys_college
    ("FK sys_user.college_id -> sys_college",
     "ALTER TABLE sys_user ADD CONSTRAINT fk_user_college FOREIGN KEY (college_id) REFERENCES sys_college(id) ON DELETE SET NULL ON UPDATE CASCADE"),
    ("FK sys_college.dean_id -> sys_user",
     "ALTER TABLE sys_college ADD CONSTRAINT fk_college_dean FOREIGN KEY (dean_id) REFERENCES sys_user(id) ON DELETE SET NULL ON UPDATE CASCADE"),

    # proj_project -> user / college
    ("FK proj_project.leader_id -> sys_user",
     "ALTER TABLE proj_project ADD CONSTRAINT fk_project_leader FOREIGN KEY (leader_id) REFERENCES sys_user(id) ON DELETE RESTRICT ON UPDATE CASCADE"),
    ("FK proj_project.teacher_id -> sys_user",
     "ALTER TABLE proj_project ADD CONSTRAINT fk_project_teacher FOREIGN KEY (teacher_id) REFERENCES sys_user(id) ON DELETE SET NULL ON UPDATE CASCADE"),
    ("FK proj_project.college_id -> sys_college",
     "ALTER TABLE proj_project ADD CONSTRAINT fk_project_college FOREIGN KEY (college_id) REFERENCES sys_college(id) ON DELETE RESTRICT ON UPDATE CASCADE"),

    # proj_team_member
    ("FK proj_team_member.project_id -> proj_project",
     "ALTER TABLE proj_team_member ADD CONSTRAINT fk_team_project FOREIGN KEY (project_id) REFERENCES proj_project(id) ON DELETE CASCADE ON UPDATE CASCADE"),
    ("FK proj_team_member.student_id -> sys_user",
     "ALTER TABLE proj_team_member ADD CONSTRAINT fk_team_student FOREIGN KEY (student_id) REFERENCES sys_user(id) ON DELETE RESTRICT ON UPDATE CASCADE"),

    # proj_review
    ("FK proj_review.project_id -> proj_project",
     "ALTER TABLE proj_review ADD CONSTRAINT fk_review_project FOREIGN KEY (project_id) REFERENCES proj_project(id) ON DELETE CASCADE ON UPDATE CASCADE"),
    ("FK proj_review.reviewer_id -> sys_user",
     "ALTER TABLE proj_review ADD CONSTRAINT fk_review_reviewer FOREIGN KEY (reviewer_id) REFERENCES sys_user(id) ON DELETE RESTRICT ON UPDATE CASCADE"),

    # proj_budget
    ("FK proj_budget.project_id -> proj_project",
     "ALTER TABLE proj_budget ADD CONSTRAINT fk_budget_project FOREIGN KEY (project_id) REFERENCES proj_project(id) ON DELETE CASCADE ON UPDATE CASCADE"),

    # proj_expense
    ("FK proj_expense.project_id -> proj_project",
     "ALTER TABLE proj_expense ADD CONSTRAINT fk_expense_project FOREIGN KEY (project_id) REFERENCES proj_project(id) ON DELETE CASCADE ON UPDATE CASCADE"),
    ("FK proj_expense.applicant_id -> sys_user",
     "ALTER TABLE proj_expense ADD CONSTRAINT fk_expense_applicant FOREIGN KEY (applicant_id) REFERENCES sys_user(id) ON DELETE RESTRICT ON UPDATE CASCADE"),
    ("FK proj_expense.budget_item_id -> proj_budget",
     "ALTER TABLE proj_expense ADD CONSTRAINT fk_expense_budget_item FOREIGN KEY (budget_item_id) REFERENCES proj_budget(id) ON DELETE SET NULL ON UPDATE CASCADE"),

    # proj_achievement
    ("FK proj_achievement.project_id -> proj_project",
     "ALTER TABLE proj_achievement ADD CONSTRAINT fk_achievement_project FOREIGN KEY (project_id) REFERENCES proj_project(id) ON DELETE CASCADE ON UPDATE CASCADE"),

    # sys_attachment
    ("FK sys_attachment.uploader_id -> sys_user",
     "ALTER TABLE sys_attachment ADD CONSTRAINT fk_attachment_uploader FOREIGN KEY (uploader_id) REFERENCES sys_user(id) ON DELETE RESTRICT ON UPDATE CASCADE"),

    # proj_midterm_check
    ("FK proj_midterm_check.project_id -> proj_project",
     "ALTER TABLE proj_midterm_check ADD CONSTRAINT fk_midterm_project FOREIGN KEY (project_id) REFERENCES proj_project(id) ON DELETE CASCADE ON UPDATE CASCADE"),
    ("FK proj_midterm_check.reviewer_id -> sys_user",
     "ALTER TABLE proj_midterm_check ADD CONSTRAINT fk_midterm_reviewer FOREIGN KEY (reviewer_id) REFERENCES sys_user(id) ON DELETE SET NULL ON UPDATE CASCADE"),

    # proj_change_request
    ("FK proj_change_request.project_id -> proj_project",
     "ALTER TABLE proj_change_request ADD CONSTRAINT fk_change_project FOREIGN KEY (project_id) REFERENCES proj_project(id) ON DELETE CASCADE ON UPDATE CASCADE"),
    ("FK proj_change_request.applicant_id -> sys_user",
     "ALTER TABLE proj_change_request ADD CONSTRAINT fk_change_applicant FOREIGN KEY (applicant_id) REFERENCES sys_user(id) ON DELETE RESTRICT ON UPDATE CASCADE"),

    # sys_operation_log
    ("FK sys_operation_log.user_id -> sys_user",
     "ALTER TABLE sys_operation_log ADD CONSTRAINT fk_log_user FOREIGN KEY (user_id) REFERENCES sys_user(id) ON DELETE SET NULL ON UPDATE CASCADE"),
]


def run():
    ok = 0
    skipped = 0
    failed = []
    with engine.begin() as conn:
        for name, sql in DDL_STATEMENTS:
            try:
                conn.execute(text(sql))
                print(f"  OK   {name}")
                ok += 1
            except Exception as e:
                # 1060: duplicate column name; 1061: duplicate key name;
                # 1091: can't DROP; 1826: duplicate FK
                mysql_err = getattr(e, "orig", None)
                errno = getattr(mysql_err, "errno", None)
                msg = str(e).splitlines()[0]
                if errno in (1060, 1061, 1091, 1826):
                    print(f"  SKIP {name}  ({errno}: {msg[:100]})")
                    skipped += 1
                else:
                    print(f"  FAIL {name}  ({errno}: {msg[:200]})")
                    failed.append((name, str(e)[:300]))
    print()
    print(f"成功: {ok}   跳过(已存在): {skipped}   失败: {len(failed)}")
    if failed:
        print("\n==== 失败的语句 ====")
        for n, m in failed:
            print(f"- {n}\n    {m}")
        sys.exit(1)


if __name__ == "__main__":
    print("[P0] 开始迁移数据库 schema...")
    run()
    print("[P0] 迁移完成。")
