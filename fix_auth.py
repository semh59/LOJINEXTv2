import pathlib

p = pathlib.Path('d:/PROJECT/LOJINEXTv2/services/driver-service/src/driver_service/auth.py')
content = p.read_text(encoding='utf-8')

import re
# 1. require_admin_token
content = re.sub(
    r"# Forensic Actor Type Mapping\s*actor_type = \"ADMIN\"\s*if role == PlatformRole\.SUPER_ADMIN:\s*actor_type = \"SUPER_ADMIN\"\s*elif role == PlatformRole\.MANAGER:\s*actor_type = \"MANAGER\"\s*return AuthContext\(actor_id=actor_id, role=role, actor_type=actor_type\)",
    "return AuthContext(actor_id=actor_id, role=role)",
    content,
    flags=re.MULTILINE
)

# 2. require_admin_or_internal_token - SUPER_ADMIN
content = content.replace(
    'return AuthContext(actor_id=actor_id, role=role, actor_type="SUPER_ADMIN")',
    'return AuthContext(actor_id=actor_id, role=role)'
)

# 3. require_admin_or_internal_token - SERVICE
content = re.sub(
    r"return AuthContext\(\s*actor_id=actor_id, role=PlatformRole\.SERVICE, service_name=service_name, actor_type=\"SERVICE\"\s*\)",
    "return AuthContext(\n            actor_id=actor_id, role=PlatformRole.SERVICE, service_name=service_name\n        )",
    content,
    flags=re.MULTILINE
)

p.write_text(content, encoding='utf-8')
print("Done")
