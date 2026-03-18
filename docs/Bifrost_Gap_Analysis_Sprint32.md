# Bifrost: Gap Analysis & Sprint Planning (ADK + Mimir Hybrid RAG)

หลังจากการย้าย Bifrost ไปใช้เฟรมเวิร์ก `google-adk` และเตรียมตัวรองรับสถาปัตยกรรม Hybrid RAG Search ของ Mimir พบว่ายังมีช่องโหว่ (Gap) หรือ Tech Debt ในโค้ดปัจจุบันที่ต้องจัดการดังนี้ครับ:

## 🚨 1. Gap Analysis (ส่วนที่ขาดหายไปใน Bifrost)

### 🔴 1.1 ADK Tool Migration (Agent ปัจจุบันยังใช้ Tools ไม่ได้)
* **ปัญหา:** ตอนที่เราเขียนสคริปต์ย้าย 12 Agent เป็น `LlmAgent` ในโฟลเดอร์เราไม่ได้กำหนดพารามิเตอร์ `tools=[...]` เข้าไปให้ Agent เลย! เครื่องมือเก่าๆ ใน `bifrost/tools/` ถูกเขียนด้วย Class Inheritance ยุคก่อนหน้า ซึ่งใช้กับ ADK ตรงๆ ไม่ได้
* **การแก้ไข:** ต้องแปลง Custom Tool Class (เช่น `search_knowledge`, `list_sources`) ให้กลายเป็น Python Async Functions มาตรฐานที่ใส่ Type hints ชัดเจนเพื่อให้ ADK แปลงเป็น Tool schemas และดึงไปใช้ได้

### 🟡 1.2 Mimir Hybrid RAG Support (Agent ขาดพลัง Search)
* **ปัญหา:** โค้ดใน `bifrost.tools.mimir` ปัจจุบันถูกเขียนให้ยิงไปที่ `/api/search` และมีพารามิเตอร์ให้ Agent ใช้แค่ `query` กับ `limit`
* **การแก้ไข:** 
  1. ต้องเปลี่ยน Endpoint เป็น `/api/v1/tenants/{tenant_id}/query` ตามที่ Mimir จะอัปเดตใหม่ 
  2. ต้องเพิ่ม Parameter `mode` (เช่น `"vector"`, `"tree"`, `"hybrid"`) ใส่เข้าไปใน Signature ของ Tool เพื่อเปิดโอกาสให้ Assistant Agent สามารถ "คิด" และเลือกว่าควรใช้ Search Strategy แบบไหนกับคำถามผู้ใช้

### 🔴 1.3 Dynamic Tenant Isolation (ปัญหาข้อมูลทะลุข้าม Tenant)
* **ปัญหา:** ใน `bifrost/main.py` ตัวแปร `settings.mimir_tenant_id` ถูกโหลดเข้า Tool แบบ Hardcoded เป็น `"default"` ทั้งแพลตฟอร์ม แปลว่า Agent ทุกตัวจะแย่งกันสืบค้นในกองข้อมูลเดียวกัน
* **การแก้ไข:** ในเฟรมเวิร์ก ADK เมื่อเราสร้าง Tool ฟังก์ชัน เราต้องดึง `run_context` จาก ADK session ออกมาเพื่อดูโพรไฟล์ของผู้ใช้หรือ Agent ที่เรียกใช้ (เช่นดูว่า Request มาจาก `fenrir` ก็ยัด Header `X-Tenant-ID: fenrir`) เพื่อป้องกันข้อมูลทะลุมิติ

### 🟡 1.4 Centralized State Logging 
* **ปัญหา:** ADK โพรวายด์ระบบจัดเก็บ Session ของตัวเองลงใน SQLite (`.adk/` folder) แต่ Dashboard ของ Project ขุดข้อมูลจาก `agent_conversations` table ใน MariaDB
* **การแก้ไข:** ต้องสร้าง ADK Event Listener หรือ Hook เพื่อดูด Log ของ ADK Session ไปโยนใส่ MariaDB ตัวกลางเพื่อให้ Dashboard ดึงมาแสดงผลได้

---

## 🏃 2. Sprint Planning (แผนงานสำหรับ Bifrost)

เพื่อปิด Gap ทั้งหมดและรองรับ Mimir Sprint 31, ขอเสนอ Sprint ดังต่อไปนี้สำหรับ Project Bifrost โดยเฉพาะ:

### Sprint 32: ADK Tools Migration & Dynamic Tenants
* **ระยะเวลาดำเนินการ:** ถัดจากงาน Mimir
* **Task 1: Tools Refactoring:** เขียนฟังก์ชันเครื่องมือใหม่ในโฟลเดอร์ `bifrost/agents/tools/mimir_tools.py` โดยใช้ Python `async def` ธรรมดา
* **Task 2: Inject Context:** ใช้ `google.adk.auth` หรือ contextual variables เพื่อดึง `tenant_id` แบบ Dynamic ในแต่ละ Request 
* **Task 3: Bind Tools to Agents:** สั่ง Import ฟังก์ชันเข้าไปใส่ใน `tools=[...]` ของไฟล์ `agent.py` ทั้ง 12 ตัว

### Sprint 33: Hybrid Knowledge Hook-up & Observability
* **Task 1: Mimir Query Tool:** เพิ่ม `mode: Literal["hybrid", "vector", "tree"]` ใน Pydantic Input Model ให้ Agent ใช้งาน
* **Task 2: Observability Hook:** เขียนโค้ดดึงประวัติข้อความจาก ADK Event Loop ส่งไปเก็บบันทึกบนตาราง `agent_conversations` เพื่อให้ Dashboard บน Mimir มีข้อมูลครบถ้วน
