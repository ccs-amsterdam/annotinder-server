from tests.conftest import client
    
def test_login(coders, admin):
    res = client.get("/users/me/login", headers=admin['headers'])
    assert res.status_code == 200, res.text

    for coder in coders:
        res = client.get("/users/me/login", headers=coder['headers'])
        assert res.status_code == 200, res.text

   
    
    
