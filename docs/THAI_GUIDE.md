# DevLinker: สรุปงานและคู่มือการใช้งาน

## สรุปสิ่งที่ทำ

DevLinker ถูกวางโครงเป็นระบบ bridge แบบ modular สำหรับรับคำสั่งจากหลายช่องทาง แล้วส่งต่อไปยัง AI coding agent ภายนอก โดยรอบนี้ implement ส่วนหลักที่พร้อมต่อยอดได้ทันทีดังนี้

- ออกแบบสถาปัตยกรรมแบบแยก `domain`, `application`, `infrastructure`
- ทำ abstraction สำหรับ channel adapter, agent adapter, response formatter และ approval store
- ทำ Discord slash commands ชุดแรก: `/forge`, `/approve`, `/reject`
- ทำ Codex CLI adapter ด้วย `asyncio.subprocess`
- ทำ preview workspace สำหรับ manual approval mode
- ทำตัว diff snapshot เพื่อตรวจ file changes แม้ workspace จะไม่เป็น git repo
- ใส่ access control, rate limiting, timeout, blocked command patterns และ logging
- เพิ่ม CLI one-shot command สำหรับทดสอบนอก Discord
- เขียน unit tests สำหรับ config, workspace diff, formatter, service flow และ Codex command builder

## โฟลว์การทำงาน

1. ผู้ใช้ส่ง `/forge`
2. Discord adapter สร้าง `AgentPromptRequest`
3. `DevLinkerService` ตรวจสิทธิ์และ rate limit
4. ระบบเลือกว่าจะรันบน live workspace หรือ preview workspace
5. `CodexCLIAdapter` เรียก `codex exec`
6. ระบบเก็บ stdout, stderr, final answer และ diff ของไฟล์ที่เปลี่ยน
7. formatter แปลงผลลัพธ์ให้เหมาะกับ Discord แล้วส่งกลับ
8. ถ้าอยู่ใน `manual` mode จะต้องใช้ `/approve` หรือ `/reject`

## ไฟล์สำคัญ

- `devlinker/settings.py`: โหลด config จาก `.env` และ `config.yaml`
- `devlinker/application/service.py`: orchestration หลักของ forge/approve/reject
- `devlinker/application/workspace.py`: clone preview workspace และคำนวณ diff
- `devlinker/infrastructure/agents/codex_cli.py`: adapter สำหรับ Codex CLI
- `devlinker/infrastructure/channels/discord_adapter.py`: slash commands และ progress update
- `devlinker/infrastructure/formatters/discord_formatter.py`: จัดรูปข้อความและตัด chunk
- `devlinker/infrastructure/persistence/approval_store.py`: เก็บ approval token ลงไฟล์ JSON

## วิธีติดตั้ง

แนะนำ Python 3.11 ขึ้นไป

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
cp config.example.yaml config.yaml
```

## การตั้งค่าเบื้องต้น

ตั้งค่าใน `.env` อย่างน้อย:

```dotenv
DISCORD_TOKEN=your_token
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
DISCORD_ALLOWED_USER_IDS=123456789012345678
DEFAULT_AGENT=codex
WORKING_DIR=./workspace
APPROVAL_MODE=manual
```

ถ้าต้องการ whitelist ผ่าน role:

```dotenv
DISCORD_ALLOWED_ROLE_IDS=123456789012345678
```

## วิธีรัน

รันบอท Discord:

```bash
python -m devlinker bot
```

รันทดสอบแบบ local:

```bash
python -m devlinker run-once --prompt "สร้าง FastAPI CRUD สำหรับ todo list" --dry-run
```

รันทดสอบแล้วส่งผลไป Discord webhook:

```bash
python -m devlinker run-once --prompt "สรุปโครงสร้างโปรเจ็กต์นี้" --dry-run --send-webhook
```

ส่งข้อความทดสอบไป webhook โดยตรง:

```bash
python -m devlinker webhook-test --message "DevLinker webhook พร้อมใช้งาน"
```

รันเทสต์:

```bash
pytest
```

## ตัวอย่างการใช้งานบน Discord

```text
/forge prompt:"สร้าง FastAPI CRUD สำหรับ todo list" agent:"codex" auto_approve:false dry_run:false
```

ถ้า `APPROVAL_MODE=manual`

- ระบบจะรันใน preview workspace ก่อน
- ส่งกลับ summary, final answer, diff และ request ID
- ถ้าต้องการ apply จริง ให้ใช้ `/approve request_id:<id>`
- ถ้าไม่ต้องการ ให้ใช้ `/reject request_id:<id>`

## โหมด approval

- `manual`: ปลอดภัยที่สุดสำหรับงานแก้ไฟล์ เพราะต้องอนุมัติก่อน apply จริง
- `auto`: เหมาะกับ environment ที่เชื่อถือได้และต้องการความเร็ว
- `never`: ใช้เป็น preview only ห้ามแตะ live workspace

## ข้อเสนอแนะสำหรับรอบถัดไป

- เพิ่ม `LineAdapter` และ `TelegramAdapter`
- เพิ่มฐานข้อมูลสำหรับ job history และ audit trail
- ทำ dashboard สำหรับดู pending approvals
- รองรับ queue / worker แยก process
- รองรับ multi-agent orchestration และ persistent memory
- เพิ่ม webhook/FastAPI adapter สำหรับ web frontend
