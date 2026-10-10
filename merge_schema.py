"""
将 init_data.sql 的内容整合到 schema.sql 中
替换掉原来的 5 个内置账户数据
"""

# 读取 schema.sql
with open('d:/SoftwareEngineering/ieproject/backend/app/database/schema.sql', 'r', encoding='utf-8') as f:
    schema = f.read()

# 读取新的初始化数据
with open('d:/SoftwareEngineering/ieproject/init_data.sql', 'r', encoding='utf-8') as f:
    init_data = f.read()

# 找到初始化数据段的起止位置
# 起始："-- 初始化数据" 注释
# 结束："-- 外键约束" 注释之前
start_marker = '-- ====================================================================\n-- 初始化数据'
end_marker = '-- ====================================================================\n-- 外键约束'

start_idx = schema.find(start_marker)
end_idx = schema.find(end_marker)

if start_idx == -1 or end_idx == -1:
    print(f"ERROR: 找不到标记位 start={start_idx} end={end_idx}")
    exit(1)

print(f"原初始化数据段: 字符位置 {start_idx} ~ {end_idx} ({end_idx - start_idx} 字符)")
print(f"新初始化数据: {len(init_data)} 字符")

# 替换
new_schema = schema[:start_idx] + init_data.rstrip() + '\n\n' + schema[end_idx:]

# 写入
with open('d:/SoftwareEngineering/ieproject/backend/app/database/schema.sql', 'w', encoding='utf-8') as f:
    f.write(new_schema)

print(f"schema.sql 已更新，总大小: {len(new_schema)} 字符")
