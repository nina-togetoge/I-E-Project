"""
用户管理模块 数据访问层(CRUD)
所有数据库操作在此集中封装，路由层与服务层通过此类访问数据库
"""
from typing import Optional, List, Tuple
from sqlalchemy import or_, and_, func
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.core.deps import DataScope
from app.models import SysUser, SysCollege, SysOperationLog


class UserCRUD:
    """用户CRUD封装类"""

    # ====================================================================
    # 用户查询
    # ====================================================================
    @staticmethod
    def get_by_id(db: Session, user_id: int) -> Optional[SysUser]:
        return db.query(SysUser).filter(SysUser.id == user_id, SysUser.is_deleted == 0).first()

    @staticmethod
    def get_by_username(db: Session, username: str) -> Optional[SysUser]:
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
        """
        query = db.query(SysUser).filter(SysUser.is_deleted == 0)

        # ---- 数据权限范围过滤 ----
        if data_scope and not data_scope.scope.get("all"):
            allowed_colleges = data_scope.scope.get("college_ids")
            if allowed_colleges:
                query = query.filter(SysUser.college_id.in_(allowed_colleges))
            # 学生角色只能看自己
            if data_scope.scope.get("is_student"):
                query = query.filter(SysUser.id == data_scope.user_id)

        # ---- 关键词模糊查询 ----
        if keyword:
            kw = f"%{keyword}%"
            query = query.filter(or_(
                SysUser.username.like(kw),
                SysUser.real_name.like(kw),
                SysUser.email.like(kw),
                SysUser.phone.like(kw),
            ))
        if role is not None:
            query = query.filter(SysUser.role == role)
        if college_id is not None:
            query = query.filter(SysUser.college_id == college_id)
        if status is not None:
            query = query.filter(SysUser.status == status)

        total = query.with_entities(func.count(SysUser.id)).scalar() or 0

        # 排序
        allowed_orders = {"id", "username", "real_name", "role", "college_id", "status", "created_at", "updated_at"}
        order_col = getattr(SysUser, order_by) if order_by in allowed_orders else SysUser.created_at
        order_func = order_col.desc() if order_dir == "desc" else order_col.asc()
        users = query.order_by(order_func).offset(offset).limit(limit).all()
        return users, total

    # ====================================================================
    # 用户增删改
    # ====================================================================
    @staticmethod
    def create(db: Session, obj_in: dict) -> SysUser:
        """创建用户，自动哈希密码"""
        if "password" in obj_in:
            obj_in["password_hash"] = hash_password(obj_in.pop("password"))
        db_obj = SysUser(**obj_in)
        db.add(db_obj)
        db.flush()
        return db_obj

    @staticmethod
    def update(db: Session, db_obj: SysUser, obj_in: dict) -> SysUser:
        """更新用户，若包含password字段则自动哈希"""
        if "password" in obj_in and obj_in["password"]:
            obj_in["password_hash"] = hash_password(obj_in.pop("password"))
        for field, value in obj_in.items():
            if value is not None and hasattr(db_obj, field) and field != "id":
                setattr(db_obj, field, value)
        db.flush()
        return db_obj

    @staticmethod
    def soft_delete(db: Session, user_id: int) -> int:
        """软删除用户（标记is_deleted=1），返回受影响行数"""
        rows = db.query(SysUser).filter(SysUser.id == user_id, SysUser.is_deleted == 0) \
            .update({"is_deleted": 1}, synchronize_session=False)
        db.flush()
        return rows

    @staticmethod
    def batch_update_status(db: Session, user_ids: List[int], status: int) -> int:
        """批量启/禁用用户"""
        rows = db.query(SysUser).filter(SysUser.id.in_(user_ids), SysUser.is_deleted == 0) \
            .update({SysUser.status: status}, synchronize_session=False)
        db.flush()
        return rows

    # ====================================================================
    # 登录相关
    # ====================================================================
    @staticmethod
    def update_login_info(db: Session, user: SysUser, ip: str) -> None:
        """用户登录成功后，更新最后登录IP和时间"""
        from datetime import datetime
        user.last_login_ip = ip
        user.last_login_at = datetime.now()
        db.flush()


class CollegeCRUD:
    """学院CRUD封装类"""

    @staticmethod
    def get_by_id(db: Session, college_id: int) -> Optional[SysCollege]:
        return db.query(SysCollege).filter(SysCollege.id == college_id).first()

    @staticmethod
    def get_by_code(db: Session, code: str) -> Optional[SysCollege]:
        return db.query(SysCollege).filter(SysCollege.college_code == code).first()

    @staticmethod
    def list_all(db: Session, include_disabled: bool = False) -> List[SysCollege]:
        q = db.query(SysCollege)
        if not include_disabled:
            q = q.filter(SysCollege.status == 1)
        return q.order_by(SysCollege.sort_order.asc(), SysCollege.id.asc()).all()

    @staticmethod
    def create(db: Session, obj_in: dict) -> SysCollege:
        obj = SysCollege(**obj_in)
        db.add(obj)
        db.flush()
        return obj

    @staticmethod
    def update(db: Session, db_obj: SysCollege, obj_in: dict) -> SysCollege:
        for f, v in obj_in.items():
            if v is not None and hasattr(db_obj, f) and f != "id":
                setattr(db_obj, f, v)
        db.flush()
        return db_obj


class OperationLogCRUD:
    """操作日志CRUD"""

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
        start_time: Optional = None,
        end_time: Optional = None,
        order_dir: str = "desc",
    ) -> Tuple[List[SysOperationLog], int]:
        q = db.query(SysOperationLog)
        if keyword:
            kw = f"%{keyword}%"
            q = q.filter(or_(
                SysOperationLog.username.like(kw),
                SysOperationLog.real_name.like(kw),
                SysOperationLog.operation_desc.like(kw),
                SysOperationLog.request_url.like(kw),
                SysOperationLog.ip_address.like(kw),
            ))
        if module_name:
            q = q.filter(SysOperationLog.module_name == module_name)
        if operation_type:
            q = q.filter(SysOperationLog.operation_type == operation_type)
        if user_id:
            q = q.filter(SysOperationLog.user_id == user_id)
        if start_time:
            q = q.filter(SysOperationLog.operation_time >= start_time)
        if end_time:
            q = q.filter(SysOperationLog.operation_time <= end_time)
        total = q.with_entities(func.count(SysOperationLog.id)).scalar() or 0
        order_col = SysOperationLog.operation_time.desc() if order_dir == "desc" \
            else SysOperationLog.operation_time.asc()
        items = q.order_by(order_col).offset(offset).limit(limit).all()
        return items, total

    @staticmethod
    def list_all_for_export(db: Session, **filters) -> List[SysOperationLog]:
        """导出用：不分页，最多导1万条"""
        items, _ = OperationLogCRUD.paginate(db, offset=0, limit=10000, **filters)
        return items
