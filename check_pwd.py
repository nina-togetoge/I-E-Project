import bcrypt

full_hash = b'$2b$12$BkvT/g5j4FB6WBPDYjWIHe53NopXAA4jq.fL02krwlW51bP3z1C9W'

for pwd in ['123456', 'admin123', '000000', '111111', '654321']:
    ok = bcrypt.checkpw(pwd.encode(), full_hash)
    print(f'密码 {pwd!r} 验证结果: {ok}')
