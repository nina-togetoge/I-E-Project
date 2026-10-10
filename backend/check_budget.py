import pymysql
from app.core.config import settings

conn = pymysql.connect(
    host=settings.DB_HOST, port=settings.DB_PORT,
    user=settings.DB_USER, password=settings.DB_PASSWORD,
    database=settings.DB_NAME, charset='utf8mb4'
)
cur = conn.cursor()
cur.execute("SELECT budget_item, HEX(budget_item) FROM proj_budget WHERE budget_item NOT IN ('劳务费','差旅费','材料费','设备费')")
for r in cur.fetchall():
    print(r)
