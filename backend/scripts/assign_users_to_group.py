#!/usr/bin/env python3
"""
Bulk-assign users to a Django auth group.

Edit USERNAMES and TARGET_GROUP_NAME below, then run:
    python backend/scripts/assign_users_to_group.py
"""

from pathlib import Path
import os
import sys


# ====== Fill these values ======
USERNAMES = [
    # "alice",
    # "bob",
    "paul"
]


# USERNAMES = [
#     "timon",
#     "rohrp7",
#     "damianpiller",
#     "alphz1",
#     "langa3",
#     "lmf123",
#     "dobrl2",
#     "TomTom",
#     "darioomartig",
#     "gurtny",
#     "dazu",
#     "niecp1",
#     "Mikey",
#     "test999",
#     "Miau",
#     "LaurinMiau",
#     "Leo",
#     "Karn",
#     "qosie1",
#     "Bi",
#     "AlTi",
# ]


# USERNAMES = [
#     "Habisan",
#     "Tschugger93",
#     "doutaz",
#     "BF08",
#     "spahrsilvio@gmail.com",
#     "julien.widmer",
#     "Damian",
#     "michaeljhla",
#     "Bella",
#     "rabia",
#     "calsa-demo",
#     "syam0591",
#     "vinu",
#     "CJ",
#     "79tM",
#     "thanush",
#     "loru",
#     "skj",
#     "calso-demo",
#     "kosik1",
#     "Sandra",
# ]

TARGET_GROUP_NAME = "ca_users"

# Optional: remove users from these groups before adding TARGET_GROUP_NAME.
REMOVE_FROM_GROUPS = [
    # "ca_cggf_users",
]

# Set to False to apply changes.
DRY_RUN = True
# ==============================


def main() -> int:
    script_path = Path(__file__).resolve()
    backend_dir = script_path.parents[1]
    sys.path.insert(0, str(backend_dir))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mysite.settings")

    import django  # pylint: disable=import-outside-toplevel

    django.setup()

    from django.contrib.auth import get_user_model  # pylint: disable=import-outside-toplevel
    from django.contrib.auth.models import Group  # pylint: disable=import-outside-toplevel

    usernames = [u.strip() for u in USERNAMES if u and u.strip()]
    if not usernames:
        print("No usernames provided. Set USERNAMES at the top of the script.")
        return 1

    target_group, _ = Group.objects.get_or_create(name=TARGET_GROUP_NAME.strip())
    remove_groups = [
        Group.objects.get_or_create(name=name.strip())[0]
        for name in REMOVE_FROM_GROUPS
        if name and name.strip()
    ]

    user_model = get_user_model()
    matched = 0
    missing = []

    print(f"Target group: {target_group.name}")
    print(f"Dry run: {DRY_RUN}")
    print("-" * 40)

    for username in usernames:
        user = user_model.objects.filter(username=username).first()
        if not user:
            missing.append(username)
            continue
        matched += 1

        print(f"[FOUND] {username}")
        if DRY_RUN:
            continue

        for grp in remove_groups:
            user.groups.remove(grp)
        user.groups.add(target_group)

    print("-" * 40)
    print(f"Processed usernames: {len(usernames)}")
    print(f"Found users: {matched}")
    print(f"Missing users: {len(missing)}")
    if missing:
        print("Missing list:", ", ".join(missing))
    if DRY_RUN:
        print("No DB changes applied (DRY_RUN=True).")
    else:
        print("Done. Group assignments updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
