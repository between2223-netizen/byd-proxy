# main.py — BYD Arabic Proxy Server v4.0

# يعمل على Railway.app | Python 3.11+

# المكتبة: github.com/jkaberg/pyBYD

from **future** import annotations
import time, os, logging
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from pybyd import BydClient, BydConfig
from pybyd.exceptions import BydAuthenticationError, BydApiError, BydRemoteControlError
from pybyd.models import ClimateStartParams, minutes_to_time_span

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(“byd-proxy”)

app = FastAPI(title=“BYD Arabic Proxy”, version=“4.0”)

app.add_middleware(
CORSMiddleware,
allow_origins=[”*”],
allow_credentials=True,
allow_methods=[”*”],
allow_headers=[”*”],
)

sessions: dict[str, dict] = {}

# ── نماذج البيانات ──────────────────────────────────────

class LoginReq(BaseModel):
username:    str
password:    str
control_pin: Optional[str] = “”
region:      str = “overseas”
country:     str = “OM”

class SessionReq(BaseModel):
session_id: str
vin:        Optional[str] = None

class ClimateReq(BaseModel):
session_id:       str
vin:              Optional[str] = None
temperature:      float = 22.0
duration_minutes: int   = 20

# ── صحة السيرفر ─────────────────────────────────────────

@app.get(”/”)
async def health():
return {“ok”: True, “service”: “BYD Arabic Proxy”, “version”: “4.0”, “sessions”: len(sessions)}

# ── تسجيل الدخول ────────────────────────────────────────

@app.post(”/login”)
async def login(req: LoginReq):
base_url = (
“https://dilinksuperappserver-cn.byd.auto”
if req.region == “cn”
else “https://dilinkappoversea-eu.byd.auto”
)
try:
cfg = BydConfig(
username=req.username,
password=req.password,
control_pin=req.control_pin or “”,
base_url=base_url,
country_code=req.country,
)
client = BydClient(cfg)
await client.login()
vehicles = await client.get_vehicles()
if not vehicles:
await client.close()
raise HTTPException(404, detail=“لا توجد سيارات مرتبطة بهذا الحساب”)

```
    sid = f"s_{int(time.time() * 1000)}"
    sessions[sid] = {
        "client":   client,
        "vehicles": [{"vin": v.vin, "model": getattr(v, "model", "BYD")} for v in vehicles],
        "created":  time.time(),
    }
    log.info(f"Login OK: {req.username}")
    return {"success": True, "session_id": sid, "vehicles": sessions[sid]["vehicles"]}

except BydAuthenticationError as e:
    raise HTTPException(401, detail=f"اسم المستخدم أو كلمة المرور خاطئة: {e}")
except HTTPException:
    raise
except Exception as e:
    log.exception("Login error")
    raise HTTPException(500, detail=f"خطأ في تسجيل الدخول: {e}")
```

# ── حالة السيارة ────────────────────────────────────────

@app.post(”/car/status”)
async def car_status(req: SessionReq):
s = _sess(req.session_id)
c = s[“client”]
vin = req.vin or s[“vehicles”][0][“vin”]
try:
rt  = await c.get_vehicle_realtime(vin)
gps = await c.get_gps_info(vin)
return {
“success”:     True,
“battery_pct”: getattr(rt,  “elec_percent”,          0),
“ev_range”:    getattr(rt,  “endurance_mileage”,      0),
“fuel_pct”:    getattr(rt,  “fuel_percent”,           0),
“fuel_range”:  getattr(rt,  “fuel_endurance_mileage”, 0),
“speed”:       getattr(rt,  “speed”,                  0),
“odometer”:    getattr(rt,  “mileage”,                0),
“locked”:      getattr(rt,  “lock_status”,            True),
“charging”:    getattr(rt,  “charging_status”,        False),
“ext_temp”:    getattr(rt,  “outdoor_temp”,           0),
“lat”:         getattr(gps, “latitude”,               0.0),
“lng”:         getattr(gps, “longitude”,              0.0),
“heading”:     getattr(gps, “heading”,                0),
“ts”:          int(time.time()),
}
except BydApiError as e:
raise HTTPException(502, detail=str(e))
except Exception as e:
raise HTTPException(500, detail=str(e))

# ── أوامر التحكم ────────────────────────────────────────

@app.post(”/car/lock”)
async def car_lock(req: SessionReq):
c, vin = _cv(req)
try:
r = await c.lock(vin)
return {“success”: r.success, “msg”: “🔒 تم القفل”}
except BydRemoteControlError as e:
raise HTTPException(403, detail=f”تحقق من PIN التحكم: {e}”)
except Exception as e:
raise HTTPException(500, detail=str(e))

@app.post(”/car/unlock”)
async def car_unlock(req: SessionReq):
c, vin = _cv(req)
try:
r = await c.unlock(vin)
return {“success”: r.success, “msg”: “🔓 تم الفتح”}
except BydRemoteControlError as e:
raise HTTPException(403, detail=f”تحقق من PIN التحكم: {e}”)
except Exception as e:
raise HTTPException(500, detail=str(e))

@app.post(”/car/horn”)
async def car_horn(req: SessionReq):
c, vin = _cv(req)
try:
fn = getattr(c, “honk_and_flash”, None) or getattr(c, “honk_horn”, None)
if not fn:
raise HTTPException(501, “دالة البوق غير متاحة”)
r = await fn(vin)
return {“success”: r.success, “msg”: “📢 تم تشغيل البوق”}
except HTTPException:
raise
except Exception as e:
raise HTTPException(500, detail=str(e))

@app.post(”/car/flash”)
async def car_flash(req: SessionReq):
c, vin = _cv(req)
try:
fn = getattr(c, “flash_lights”, None) or getattr(c, “honk_and_flash”, None)
if not fn:
raise HTTPException(501, “دالة الأضواء غير متاحة”)
r = await fn(vin)
return {“success”: r.success, “msg”: “💡 تم تشغيل الأضواء”}
except HTTPException:
raise
except Exception as e:
raise HTTPException(500, detail=str(e))

@app.post(”/car/climate/start”)
async def climate_start(req: ClimateReq):
s = _sess(req.session_id)
c = s[“client”]
vin = req.vin or s[“vehicles”][0][“vin”]
try:
params = ClimateStartParams(
temperature=req.temperature,
time_span=minutes_to_time_span(req.duration_minutes),
)
r = await c.start_climate(vin, params=params)
return {“success”: r.success, “msg”: f”❄️ تكييف {req.temperature}° / {req.duration_minutes} دقيقة”}
except BydRemoteControlError as e:
raise HTTPException(403, detail=f”تحقق من PIN التحكم: {e}”)
except Exception as e:
raise HTTPException(500, detail=str(e))

@app.post(”/car/climate/stop”)
async def climate_stop(req: SessionReq):
c, vin = _cv(req)
try:
r = await c.stop_climate(vin)
return {“success”: r.success, “msg”: “✅ تم إيقاف التكييف”}
except Exception as e:
raise HTTPException(500, detail=str(e))

@app.post(”/car/gps”)
async def car_gps(req: SessionReq):
c, vin = _cv(req)
try:
g = await c.get_gps_info(vin)
return {
“success”: True,
“lat”:     g.latitude,
“lng”:     g.longitude,
“heading”: getattr(g, “heading”, 0),
“speed”:   getattr(g, “speed”,   0),
“ts”:      int(time.time()),
}
except Exception as e:
raise HTTPException(500, detail=str(e))

@app.post(”/logout”)
async def logout(req: SessionReq):
if req.session_id in sessions:
try:
await sessions[req.session_id][“client”].close()
except Exception:
pass
del sessions[req.session_id]
return {“success”: True}

# ── دوال مساعدة ─────────────────────────────────────────

def _sess(sid: str) -> dict:
if sid not in sessions:
raise HTTPException(401, detail=“الجلسة منتهية — سجّل الدخول مجدداً”)
expired = [k for k, v in sessions.items() if time.time() - v[“created”] > 86400]
for k in expired:
del sessions[k]
return sessions[sid]

def _cv(req: SessionReq):
s = _sess(req.session_id)
return s[“client”], (req.vin or s[“vehicles”][0][“vin”])

# ────────────────────────────────────────────────────────

if **name** == “**main**”:
import uvicorn
uvicorn.run(“main:app”, host=“0.0.0.0”, port=int(os.getenv(“PORT”, 8000)))
