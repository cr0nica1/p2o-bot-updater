from updater.presentation.discord_bot.permissions import has_admin_role


class FakeRole:
    def __init__(self, role_id):
        self.id = role_id


class FakeMember:
    def __init__(self, role_ids):
        self.roles = [FakeRole(r) for r in role_ids]


def test_member_with_admin_role_passes():
    member = FakeMember([100, 333, 200])
    assert has_admin_role(member, admin_role_id=333) is True


def test_member_without_admin_role_fails():
    member = FakeMember([100, 200])
    assert has_admin_role(member, admin_role_id=333) is False


def test_user_without_roles_attribute_fails():
    class UserOnly:
        pass

    assert has_admin_role(UserOnly(), admin_role_id=333) is False
