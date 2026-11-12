import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from amplifier.server import create_server, valid_url

class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.server=create_server(str(Path(self.tmp.name)/"db.sqlite3"),
            "admin@example.test","Long-Example-Password-123!",port=0,secure=False)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.tmp.cleanup)
        self.cookie=None;self.csrf=None
    def send(self, method, route, obj=None, cookie=None, csrf=None):
        client=http.client.HTTPConnection("127.0.0.1",self.server.server_address[1],timeout=5)
        headers={}
        if obj is not None:headers["Content-Type"]="application/json"
        if cookie:headers["Cookie"]=cookie
        if csrf:headers["X-CSRF-Token"]=csrf
        client.request(method,route,json.dumps(obj) if obj is not None else None,headers)
        res=client.getresponse()
        raw=res.read()
        out=res.status,json.loads(raw) if res.getheader("Content-Type","").startswith("application/json") else raw,dict(res.getheaders())
        client.close()
        return out
    def login(self,email="admin@example.test",password="Long-Example-Password-123!"):
        status,data,hdr=self.send("POST","/api/login",{"email":email,"password":password})
        self.assertEqual(status,200,data)
        return hdr["Set-Cookie"].split(";")[0],data["csrf"]
    def logged(self,method,path,body=None):
        if not self.cookie:self.cookie,self.csrf=self.login()
        return self.send(method,path,body,self.cookie,self.csrf)
    def campaign(self):
        s,r,_=self.logged("POST","/api/campaigns",{"name":"Transformations","goal":5000,"target_metric":"views"})
        self.assertEqual(s,201,r)
        return r["id"]
    def asset(self):
        s,r,_=self.logged("POST","/api/assets",{"campaign_id":self.campaign(),"platform":"youtube",
            "title":"Transformation podcast","url":"https://youtu.be/abc"})
        self.assertEqual(s,201,r)
        return r["id"]
    def test_health(self):
        self.assertEqual(self.send("GET","/health")[0],200)
        self.assertEqual(self.send("GET","/")[0],200)
    def test_authentication(self):
        self.assertEqual(self.send("GET","/api/me")[0],401)
        self.assertEqual(self.send("POST","/api/login",{"email":"admin@example.test","password":"bad"})[0],401)
        cookie,_=self.login()
        self.assertEqual(self.send("GET","/api/me",cookie=cookie)[0],200)
    def test_csrf(self):
        cookie,_=self.login()
        self.assertEqual(self.send("POST","/api/campaigns",
            {"name":"Denied","goal":1,"target_metric":"views"},cookie=cookie)[0],403)
    def test_campaign_assets(self):
        self.asset()
        self.assertEqual(len(self.logged("GET","/api/campaigns")[1]["campaigns"]),1)
        self.assertEqual(len(self.logged("GET","/api/assets")[1]["assets"]),1)
    def test_redirect_count_is_not_view(self):
        rid=self.asset()
        status,_,headers=self.logged("GET","/out/"+rid)
        self.assertEqual(status,302)
        self.assertEqual(headers["Location"],"https://youtu.be/abc")
        stats=self.logged("GET","/api/stats")[1]
        self.assertEqual(stats["outbound_opens"],1)
        self.assertIsNone(stats["verified_platform_metrics"])
    def test_unsafe_url_rejected(self):
        for bad in ("http://linkedin.com/posts/a","https://linkedin.com.evil.test/posts/a",
                    "https://x.com/status/abc","javascript:alert(1)"):
            with self.assertRaises(ValueError):
                valid_url("linkedin",bad)
    def test_metrics_are_unverified(self):
        rid=self.asset()
        status,data,_=self.logged("POST","/api/metrics",
            {"asset_id":rid,"name":"views","value":42,"source":"manual"})
        self.assertEqual(status,201)
        self.assertFalse(data["verified"])
        self.assertEqual(self.logged("POST","/api/metrics",
            {"asset_id":rid,"name":"views","value":42,"source":"official"})[0],400)
    def test_workspace_isolation(self):
        rid=self.asset()
        status,body,_=self.logged("POST","/api/workspaces",
            {"name":"Other client","admin_email":"other@example.test",
             "admin_password":"Another-Long-Password-123!"})
        self.assertEqual(status,201)
        other_cookie,other_csrf=self.login("other@example.test","Another-Long-Password-123!")
        self.assertEqual(self.send("GET","/api/assets",cookie=other_cookie)[1]["assets"],[])
        self.assertEqual(self.send("GET","/out/"+rid,cookie=other_cookie)[0],404)

if __name__=="__main__":
    unittest.main()
