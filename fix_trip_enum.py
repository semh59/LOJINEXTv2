import pathlib
import re

import_repl = "from platform_auth import PlatformActorType, PlatformRole"

for filepath in [
    'd:/PROJECT/LOJINEXTv2/services/trip-service/src/trip_service/routers/trips.py',
    'd:/PROJECT/LOJINEXTv2/services/trip-service/src/trip_service/trip_helpers.py'
]:
    p = pathlib.Path(filepath)
    if not p.exists(): continue
    c = p.read_text(encoding='utf-8')
    
    # Imports
    c = re.sub(r"from trip_service\.enums import(.*?)ActorType,?s*(.*?)", r"from trip_service.enums import \1\2\nfrom platform_auth import PlatformRole, PlatformActorType", c)
    c = c.replace(", \nfrom platform_auth", "\nfrom platform_auth")
    c = c.replace("import \nfrom platform_auth", "import \nfrom platform_auth") # dirty cleanup if empty

    if "ActorType" in c:
        if "from platform_auth import PlatformRole" not in c:
            c = "from platform_auth import PlatformRole, PlatformActorType\n" + c
    
    # Roles
    c = c.replace("ActorType.SUPER_ADMIN.value", "PlatformRole.SUPER_ADMIN.value")
    c = c.replace("ActorType.MANAGER.value", "PlatformRole.MANAGER.value")
    c = c.replace("ActorType.OPERATOR.value", "PlatformRole.OPERATOR.value")
    c = c.replace("ActorType.SERVICE.value", "PlatformRole.SERVICE.value")
    
    # Generic usages of ActorType
    c = c.replace("ActorType.SERVICE", "PlatformActorType.SERVICE")
    c = c.replace("ActorType.SYSTEM", "PlatformActorType.SYSTEM")
    c = c.replace("ActorType.DRIVER", "PlatformActorType.DRIVER")

    # Specifically for "ActorType," in imports lines with multi-line
    c = c.replace("    ActorType,\n", "    PlatformRole,\n    PlatformActorType,\n")
    
    p.write_text(c, encoding='utf-8')

# Remove ActorType from trip_service/enums.py
enum_p = pathlib.Path('d:/PROJECT/LOJINEXTv2/services/trip-service/src/trip_service/enums.py')
ec = enum_p.read_text(encoding='utf-8')
ec = re.sub(r"class ActorType\(str, enum\.Enum\):.*?(?=\n\nclass|\Z)", "", ec, flags=re.DOTALL)
enum_p.write_text(ec, encoding='utf-8')

print("Refactored ActorType")
