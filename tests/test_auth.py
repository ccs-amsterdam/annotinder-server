from annotinder import auth
from annotinder.models import User


def test_token(user):
    assert not auth.verify_token("Dit is geen token")
    token = auth.get_token(user)
    assert auth.verify_token(token)


def test_password(user):
    assert not auth.verify_password(user.email, "test")
    auth.change_password(user, "test")
    assert auth.verify_password(user.email, "test")
    assert not auth.verify_password(user, "geen test")
