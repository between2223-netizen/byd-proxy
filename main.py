# main.py — BYD Arabic App Backend

# يعمل على Railway.app | Python 3.11+

# يستخدم مكتبة pyBYD التي تتجاوز تشفير WBSK/Bangcle تلقائياً

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
import time, os

from pybyd import BydClient, BydConfig
from pybyd.models import ClimateStartParams, minutes_to_time_span

# ============================================================

app = FastAPI(title=“BYD Arabic Proxy”, version=“3.0”)

app.add_middleware(
CORSMiddleware,
allow_origins=[”*”],
allow_methods=[”*”],
allow_headers=[”*”],
)

# جلسات في الذاكرة — session_id → {client, vehicles, created}

sessions: dict = {}

# ============================================================

# نماذج البيانات

# ============================================================

class LoginReq(BaseModel):
username: str
password: str
control_pin: Optional[str] = “”
region: str = “overseas”   # “overseas” أو “cn”
country_code: str = “OM”

class SessionReq(BaseModel):
session_id: str
vin: Optional[str] = None

class ClimateReq(BaseModel):
session_id: str
vin: Optional[str] = None
temperature: float = 22.0
duration_minutes: int = 20

# ============================================================

# مسار الصحة

# ============================================================

@app.get(”/”)
async def health():
return {
“status”: “✅ يعمل”,
“sessions”: len(sessions),
“version”: “3.0”
}

# ============================================================

# تسجيل الدخول

# ============================================================

@app.post(”/login”)
async def login(req: LoginReq):
try:
base = (
“https://dilinksuperappserver-cn.byd.auto”
if req.region == “cn”
else “https://dilinkappoversea-eu.byd.auto”
)
cfg = BydConfig(
username=req.username,
password=req.password,
control_pin=req.control_pin or “”,
base_url=base,
country_code=req.country_code,
)
client = BydClient(cfg)
await client.login()
vehicles = await client.get_vehicles()
if not vehicles:
raise HTTPException(404, “لا توجد سيارات مرتبطة”)

```
    sid = f"s_{int(time.time()*1000)}"
    sessions[sid] = {
        "client": client,
        "vehicles": [{"vin": v.vin, "model": getattr(v,"model","BYD")} for v in vehicles],
        "created": time.time(),
    }
    return {
        "success": True,
        "session_id": sid,
        "vehicles": sessions[sid]["vehicles"],
    }
except HTTPException:
    raise
except Exception as e:
    raise HTTPException(401, f"فشل تسجيل الدخول: {e}")
```

# ============================================================

# حالة السيارة

# ============================================================

@app.post(”/car/status”)
async def status(req: SessionReq):
s = _sess(req.session_id)
c: BydClient = s[“client”]
vin = req.vin or s[“vehicles”][0][“vin”]
try:
rt  = await c.get_vehicle_realtime(vin)
gps = await c.get_gps_info(vin)
return {
“success”: True,
“battery_pct”:   getattr(rt,  “elec_percent”, 0),
“ev_range”:      getattr(rt,  “endurance_mileage”, 0),
“fuel_pct”:      getattr(rt,  “fuel_percent”, 0),
“fuel_range”:    getattr(rt,  “fuel_endurance_mileage”, 0),
“speed”:         getattr(rt,  “speed”, 0),
“odometer”:      getattr(rt,  “mileage”, 0),
“locked”:        getattr(rt,  “lock_status”, True),
“charging”:      getattr(rt,  “charging_status”, False),
“ext_temp”:      getattr(rt,  “outdoor_temp”, 0),
“lat”:           getattr(gps, “latitude”, 0),
“lng”:           getattr(gps, “longitude”, 0),
“heading”:       getattr(gps, “heading”, 0),
“ts”:            int(time.time()),
}
except Exception as e:
raise HTTPException(500, str(e))

# ============================================================

# أوامر التحكم

# ============================================================

@app.post(”/car/lock”)
async def lock(req: SessionReq):
s = _sess(req.session_id); c: BydClient = s[“client”]
vin = req.vin or s[“vehicles”][0][“vin”]
try:
r = await c.lock(vin)
return {“success”: r.success, “msg”: “🔒 تم القفل”}
except Exception as e:
raise HTTPException(500, str(e))

@app.post(”/car/unlock”)
async def unlock(req: SessionReq):
s = _sess(req.session_id); c: BydClient = s[“client”]
vin = req.vin or s[“vehicles”][0][“vin”]
try:
r = await c.unlock(vin)
return {“success”: r.success, “msg”: “🔓 تم الفتح”}
except Exception as e:
raise HTTPException(500, str(e))

@app.post(”/car/horn”)
async def horn(req: SessionReq):
s = _sess(req.session_id); c: BydClient = s[“client”]
vin = req.vin or s[“vehicles”][0][“vin”]
try:
r = await c.honk_horn(vin)
return {“success”: r.success, “msg”: “📢 تم تشغيل البوق”}
except Exception as e:
raise HTTPException(500, str(e))

@app.post(”/car/flash”)
async def flash(req: SessionReq):
s = _sess(req.session_id); c: BydClient = s[“client”]
vin = req.vin or s[“vehicles”][0][“vin”]
try:
r = await c.flash_lights(vin)
return {“success”: r.success, “msg”: “💡 تم تشغيل الأضواء”}
except Exception as e:
raise HTTPException(500, str(e))

@app.post(”/car/climate/start”)
async def climate_start(req: ClimateReq):
s = _sess(req.session_id); c: BydClient = s[“client”]
vin = req.vin or s[“vehicles”][0][“vin”]
try:
params = ClimateStartParams(
temperature=req.temperature,
time_span=minutes_to_time_span(req.duration_minutes),
)
r = await c.start_climate(vin, params=params)
return {“success”: r.success, “msg”: f”❄️ تكييف {req.temperature}° لمدة {req.duration_minutes} دقيقة”}
except Exception as e:
raise HTTPException(500, str(e))

@app.post(”/car/climate/stop”)
async def climate_stop(req: SessionReq):
s = _sess(req.session_id); c: BydClient = s[“client”]
vin = req.vin or s[“vehicles”][0][“vin”]
try:
r = await c.stop_climate(vin)
return {“success”: r.success, “msg”: “✅ تم إيقاف التكييف”}
except Exception as e:
raise HTTPException(500, str(e))

@app.post(”/car/gps”)
async def gps(req: SessionReq):
s = _sess(req.session_id); c: BydClient = s[“client”]
vin = req.vin or s[“vehicles”][0][“vin”]
try:
g = await c.get_gps_info(vin)
return {“success”: True, “lat”: g.latitude, “lng”: g.longitude,
“heading”: getattr(g,“heading”,0), “speed”: getattr(g,“speed”,0)}
except Exception as e:
raise HTTPException(500, str(e))

@app.post(”/logout”)
async def logout(req: SessionReq):
if req.session_id in sessions:
try: await sessions[req.session_id][“client”].close()
except: pass
del sessions[req.session_id]
return {“success”: True}

# ============================================================

# مساعد الجلسة

# ============================================================

def _sess(sid: str) -> dict:
if sid not in sessions:
raise HTTPException(401, “الجلسة منتهية — سجّل الدخول مجدداً”)
# تنظيف الجلسات القديمة (+24 ساعة)
old = [k for k,v in sessions.items() if time.time()-v[“created”] > 86400]
for k in old:
del sessions[k]
return sessions[sid]

# ============================================================

if **name** == “**main**”:
import uvicorn
uvicorn.run(app, host=“0.0.0.0”, port=int(os.getenv(“PORT”, 8000)))
