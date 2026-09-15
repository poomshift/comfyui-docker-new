# comfy-agent — Design (ComfyUI skill for AI agents)

วันที่: 2026-09-15
สถานะ: ร่างเพื่อรีวิว (ยังไม่ implement)

## 1. เป้าหมาย

ให้ AI agent ที่มี shell (Claude Code, Codex, Cursor agent ฯลฯ) ใช้ ComfyUI เป็นเครื่องมือสร้างภาพและวิดีโอได้
โดย ComfyUI นั้นจะรันบนเครื่อง user หรือบน RunPod จาก image ของ repo นี้ก็ได้ และ user ต่อยอด
เขียน skill เฉพาะงานของตัวเองบนฐานนี้ได้โดยไม่ต้องรู้ API ของ ComfyUI

สิ่งที่ต้องทำได้
- รัน workflow จากไฟล์ของ user (API format) และจาก official templates ของ ComfyUI
- แก้ค่าใน workflow ด้วยชื่อที่มนุษย์อ่านออก ไม่ใช่ node id
- ตรวจก่อนรันว่า node และโมเดลที่ workflow อ้างถึงมีจริงบนเครื่องปลายทาง
- จัดการกรณี **ชื่อไฟล์โมเดลใน workflow ไม่ตรงกับที่ติดตั้ง** อย่างปลอดภัย
- ส่งงานแล้วติดตามผลแบบ async ทนต่อ RunPod proxy ที่ตัด request เกิน 100 วินาที และทนต่อ timeout ของ Bash tool ฝั่ง agent
- ดึงผลลัพธ์ลงเครื่อง user พร้อมข้อมูลว่าไฟล์นี้มาจาก workflow และค่าอะไร

นอกขอบเขต (ตั้งใจไม่ทำในเวอร์ชันแรก)
- MCP server ใน pod (ห่อทีหลังได้จาก library เดียวกัน)
- จัดการ lifecycle ของ pod (สร้าง/terminate) ผ่าน RunPod API
- แปลง workflow ที่มี subgraph, legacy group node หรือ node ที่มี dynamic input ให้ครบทุกกรณี
- Auth บนพอร์ต 8188 (เป็นเรื่องของ image ไม่ใช่ของ skill; skill แค่รองรับ header ถ้ามี)

## 2. หลักการออกแบบ

1. **API เดียว ทางเดียว** ทุกอย่างผ่าน HTTP API ของ ComfyUI ไม่แตะดิสก์ของ ComfyUI ตรงๆ แม้จะรัน local
   ทำให้ local กับ RunPod เป็นโค้ดพาธเดียวกัน
2. **Submit แล้ว poll** ไม่มี request ไหนเปิดค้างเกินไม่กี่วินาที
3. **ตรวจก่อนรัน และไม่เดาแทน user ในเรื่องที่เปลี่ยนผลลัพธ์** ชื่อโมเดลที่ต่างกันแค่ตัวพิมพ์หรือขีดให้แก้อัตโนมัติได้
   แต่ต่างกันที่ precision หรือ variant ต้องให้ agent หรือ user ตัดสินใจ
4. **Output อ่านได้ทั้งคนและเครื่อง** ทุกคำสั่งมี `--json` และ exit code ที่มีความหมาย agent จะได้ไม่ต้อง parse ข้อความ
5. **ไม่มี dependency นอก stdlib ของ Python 3.10+** user ติดตั้งได้ด้วยการ copy โฟลเดอร์เดียว
6. **Skill สอนวิธีคิด CLI ทำงานจริง** SKILL.md สั้น เก็บรายละเอียดไว้ใน references และใน `--help`

## 3. โครงสร้างไฟล์

ชื่อ skill: **`comfy-agent`** วางใน repo นี้ที่ `skills/comfy-agent/` และ user ติดตั้งโดย copy ไป `~/.claude/skills/comfy-agent/`
(หรือ `~/.agents/skills/comfy-agent/` สำหรับ runtime อื่น)

ชื่อคำสั่ง: `comfy_agent.py` (เรียกสั้นๆ ผ่าน alias `comfy-agent`) ตั้งใจไม่ใช้ชื่อ `comfy` เพราะชนกับ `comfy-cli` ของ Comfy-Org

```
skills/comfy-agent/
  SKILL.md                      # จุดเข้า ไม่เกิน 500 คำ
  scripts/
    comfy_agent.py              # CLI entry (argparse) เรียก comfylib; พิมพ์ banner ตามกฎ §5.1
    comfylib/
      __init__.py
      api.py                    # HTTP client: retry, timeout, auth header, url join
      workflow.py               # โหลด/ตรวจฟอร์แมต, address resolver, override, inspect
      models.py                 # ดึงรายการโมเดลจาก object_info + /models, fuzzy match, policy
      convert.py                # UI format -> API format (best-effort, รายงานสิ่งที่ไม่รองรับ)
      jobs.py                   # submit, status, wait, fetch, ledger
      templates.py              # official templates: list, fetch
      download.py               # สั่งดาวน์โหลดโมเดล (RunPod dashboard / local dir)
      output.py                 # human/json rendering, exit codes
  references/
    api.md                      # endpoint cheat sheet ที่ CLI ใช้ พร้อม response shape
    workflows.md                # UI vs API format, วิธี export, address syntax, official templates
    models.md                   # นโยบายจับคู่ชื่อโมเดล และวิธีตัดสินใจเมื่อไม่ตรง
    environments.md             # local vs RunPod: URL, timeouts, dashboard, terminate reminder
    troubleshooting.md          # error ที่พบบ่อย -> สาเหตุ -> คำสั่งแก้
    recipes.md                  # ลำดับคำสั่งสำหรับงานมาตรฐาน: t2i, i2v, upscale, batch
  tests/
    fixtures/                   # object_info snapshot, ตัวอย่าง workflow ทั้งสองฟอร์แมต
    test_models.py
    test_workflow.py
    test_convert.py
    test_jobs.py
```

## 4. การตั้งค่าและสภาพแวดล้อม

| ตัวแปร | จำเป็น | ความหมาย |
|---|---|---|
| `COMFY_URL` | ใช่ | base URL ของ ComfyUI เช่น `http://127.0.0.1:8188` หรือ `https://<pod>-8188.proxy.runpod.net` |
| `COMFY_AUTH` | ไม่ | `user:pass` (basic) หรือ `Bearer xxx` แนบทุก request ถ้ามี |
| `COMFY_DASHBOARD_URL` | ไม่ | dashboard 8189 ของ image นี้ ใช้สั่งดาวน์โหลดโมเดล ถ้าไม่ตั้งและ `COMFY_URL` เป็น RunPod proxy จะเดาโดยแทน `-8188` ด้วย `-8189` |
| `COMFY_MODELS_DIR` | ไม่ | สำหรับ local: โฟลเดอร์ `ComfyUI/models` ให้ `download` เขียนลงตรงได้ |
| `COMFY_OUT` | ไม่ | โฟลเดอร์ปลายทางของ `fetch` ค่าเริ่มต้น `./comfy-out` |
| `COMFY_STATE` | ไม่ | ที่เก็บ ledger ค่าเริ่มต้น `~/.comfy-agent/` |

ทุกคำสั่งรับ `--url` และ `--auth` เพื่อ override env ได้

`comfy_agent.py doctor` ตรวจ: ต่อถึงไหม, เวอร์ชัน ComfyUI, จำนวน node class, VRAM/ดิสก์จาก `/system_stats`,
เป็น RunPod proxy หรือไม่, dashboard ถึงไหม แล้วพิมพ์ข้อจำกัดที่ใช้กับสภาพแวดล้อมนี้

## 5. คำสั่ง CLI

ทุกคำสั่ง: `--json` ให้ output เป็น JSON บรรทัดเดียว, exit code ตามตาราง §11

| คำสั่ง | หน้าที่ | Request ที่ใช้ |
|---|---|---|
| `doctor` | ตรวจสภาพแวดล้อม | `/system_stats`, `/object_info` (นับ), dashboard `/api/models` |
| `templates list [--filter]` | รายการ official templates พร้อมคำอธิบายและโมเดลที่ต้องใช้ | `/api/workflow_templates`, `/templates/index.json` |
| `templates get <name> [--out f]` | ดึงไฟล์ template (UI format) ลงเครื่อง | `/templates/<name>.json` |
| `convert <ui.json> [--out api.json]` | แปลง UI -> API format รายงานสิ่งที่แปลงไม่ได้ | `/object_info` |
| `inspect <wf.json>` | แสดงช่องที่แก้ได้ พร้อม address, ค่าปัจจุบัน, ชนิด, บทบาทที่เดาได้ | `/object_info` |
| `validate <wf.json> [--set ...] [--fix-models auto]` | ตรวจ node หาย, โมเดลไม่ตรง, ค่านอกช่วง คืนรายงาน | `/object_info`, `/models/<folder>` |
| `run <wf.json> [--set ...] [--fix-models auto] [--seed random] [--wait [--timeout S]] [--out DIR]` | validate แล้วส่งงาน คืน prompt_id ทันที (หรือรอถ้า `--wait`) | `/upload/image`, `/prompt` |
| `status <prompt_id>` | queued/running/done/error พร้อม progress ถ้ามี | `/queue`, `/history/<id>` |
| `wait <prompt_id> [--timeout S]` | poll จนจบหรือครบเวลา | เดียวกับ status |
| `fetch <prompt_id> [--out DIR]` | ดาวน์โหลดทุก output ของงานนี้ พร้อม sidecar JSON | `/history/<id>`, `/view` |
| `queue` | งานที่กำลังรันและรอ | `/queue` |
| `cancel <prompt_id\|--all>` | ลบจากคิว หรือ interrupt งานที่กำลังรัน | `/queue` (delete), `/interrupt` |
| `models [folder] [--grep]` | รายการโมเดลที่ติดตั้ง | `/models`, `/models/<folder>` |
| `nodes [--grep]` | รายการ node class ที่มี | `/object_info` |
| `download <url> --type <folder> [--filename] [--wait]` | สั่งดาวน์โหลดโมเดลเข้าเครื่องปลายทาง | dashboard `POST /download/{huggingface\|civitai\|googledrive}` หรือเขียนลง `COMFY_MODELS_DIR` |
| `free [--unload-models]` | คืน VRAM | `/free` |
| `ledger [--last N]` | งานที่เคยส่งจากเครื่องนี้ พร้อมสถานะล่าสุดที่รู้ | ไฟล์ local |

`run` เป็น composite: upload ไฟล์ที่อ้างใน `--set` -> apply overrides -> validate -> submit -> บันทึก ledger
ถ้า validate ไม่ผ่านจะไม่ส่งงานและ exit 3 พร้อมรายงานเดียวกับคำสั่ง `validate`

### 5.1 Banner

`doctor` และการรันโดยไม่มี argument พิมพ์ banner นี้ไปที่ **stderr** ก่อนผลลัพธ์อื่น

```
  ____                     __         _   _  ___
 / ___|  ___   _ __ ___   / _| _   _ | | | ||_ _|
| |     / _ \ | '_ ` _ \ | |_ | | | || | | | | |
| |___ | (_) || | | | | ||  _|| |_| || |_| | | |
 \____| \___/ |_| |_| |_||_|   \__, | \___/ |___|
                               |___/
   c o m f y - a g e n t  |  by PromptAlchemist
```

กฎ: ASCII ล้วน (ใช้ `|` คั่น ไม่ใช้ middle dot) กว้างไม่เกิน 49 ตัวอักษร ไม่มีสี; **ไม่พิมพ์** เมื่อมี `--json`, เมื่อ `COMFY_QUIET=1`, หรือเมื่อ stderr ไม่ใช่ TTY
SKILL.md กำหนดให้ `doctor` เป็นคำสั่งแรกของทุก session banner จึงปรากฏตอนเริ่มใช้ skill โดยไม่ต้องพึ่งให้ agent พิมพ์เอง

## 6. การจัดการ workflow

### 6.1 ฟอร์แมต

- **API format** `{ "<id>": { "class_type", "inputs", "_meta": {"title"} } }` คือสิ่งเดียวที่ `/prompt` รับ
- **UI format** มี `nodes`, `links`, `groups`, `version` เป็นฟอร์แมตของปุ่ม Save และของ official templates ทั้งหมด

CLI ตรวจฟอร์แมตอัตโนมัติจากโครงสร้าง ถ้าได้ UI format จะเรียก `convert` ให้ในหน่วยความจำ
และเตือนว่าเป็นการแปลงแบบ best-effort ถ้าแปลงไม่ได้จะบอกให้ user export แบบ API format แทน

### 6.2 การแปลง UI -> API (convert.py)

ขั้นตอน
1. โหลด `/object_info` เพื่อรู้ลำดับและชนิด input ของแต่ละ class
2. สำหรับแต่ละ node: input ที่มี `link` -> อ้าง `[from_node, from_slot]`; input ที่เป็น widget -> อ่านจาก
   `widgets_values` ตามลำดับของ object_info (`required` แล้ว `optional`) โดยข้ามค่า `control_after_generate`
   ที่ตามหลัง `seed`/`noise_seed`
3. node ที่ `mode == 2` (muted) ตัดออก; node ที่ `mode == 4` (bypass) ต่อสายผ่านตามชนิด output ที่ตรงกับ input
4. `Reroute` ยุบทิ้ง; `PrimitiveNode` ดันค่าไปยัง widget ปลายทาง
5. เก็บ `title` ไว้ใน `_meta.title` เพื่อให้ address ด้วย `@title` ได้

ไม่รองรับและจะ **ล้มเหลวพร้อมรายชื่อ** ไม่ใช่แปลงผิดเงียบๆ: subgraph (`definitions.subgraphs`), legacy group node
(`workflow/...`), node ที่ class ไม่มีใน object_info, node ที่จำนวน `widgets_values` ไม่ตรงกับที่คาด

### 6.3 Address syntax สำหรับ `--set` และรายงาน

```
#<node_id>.<input>          # #7.text
@<title>.<input>            # "@Positive Prompt.text"  (title จาก _meta.title หรือ UI title)
<ClassType>.<input>         # KSampler.seed   (ต้อง unique มิฉะนั้น error พร้อมรายชื่อ #id)
<ClassType>[n].<input>      # CLIPTextEncode[0].text  (ลำดับตาม node id)
```

- ค่าถูกแปลงชนิดตาม object_info (INT/FLOAT/BOOLEAN/STRING/combo) ผิดชนิดหรือนอกช่วง min/max -> error ก่อนส่ง
- input ประเภทไฟล์ (เช่น `LoadImage.image`, `LoadVideo.video`, `LoadAudio.audio`) ถ้าค่าเป็น path ที่มีอยู่บนเครื่อง user
  จะ upload ผ่าน `/upload/image` ก่อนแล้วแทนด้วยชื่อไฟล์ที่ server ตอบกลับ
- `--seed random` สุ่มค่าให้ทุก input ชื่อ `seed`/`noise_seed` ที่เป็นค่าคงที่ และบันทึกค่าที่ใช้ลง sidecar
- `--set-file overrides.json` สำหรับ override หลายค่า (map address -> value)

### 6.4 inspect

จัดกลุ่มช่องที่แก้ได้ (input ที่เป็นค่าคงที่ ไม่ใช่ link) ตามบทบาทที่เดาได้จาก class และ title
- `prompt.positive` / `prompt.negative` (CLIPTextEncode และ text encoder อื่น เดาจาก title และจากสายที่ต่อเข้า `positive`/`negative` ของ sampler)
- `sampling` (seed, steps, cfg, sampler_name, scheduler, denoise, shift)
- `size` (width, height, length/frames, fps, batch_size)
- `inputs.files` (image/video/audio loaders)
- `models` (ทุก input ที่เป็น combo ของโฟลเดอร์โมเดล)
- `outputs` (SaveImage, VHS_VideoCombine ฯลฯ พร้อม filename_prefix)
- `other` ที่เหลือ

การเดาบทบาทเป็นเพียง hint สำหรับ agent; address ที่แสดงคือสิ่งที่ใช้จริง

### 6.5 Official templates

- `templates list` รวมข้อมูลจาก `/templates/index.json` (ชื่อ, หมวด, คำอธิบาย, โมเดลที่ต้องใช้ถ้ามีระบุ) และจาก
  `/api/workflow_templates` (template ที่ custom node แถมมา)
- `templates get` ดึงไฟล์ UI format; `run` กับไฟล์นี้จะผ่าน `convert` อัตโนมัติ
- เพราะ template อ้างโมเดลตามชื่อที่ทีม ComfyUI ตั้ง แต่เครื่อง user มักมีชื่ออื่น ขั้น `validate` จึงสำคัญที่สุดกับ template

## 7. การแก้ปัญหาชื่อโมเดลไม่ตรง (models.py)

### 7.1 แหล่งความจริง

สำหรับ input ที่เป็น combo ของโมเดล รายการที่ server ยอมรับคือ options ใน `/object_info` ของ input นั้นเอง
(รองรับทั้งรูป `[[...options], {}]` แบบเก่า และ `["COMBO", {"options": [...]}]` แบบใหม่)
สำรองด้วย `/models/<folder>` เมื่อ combo ว่างหรือเป็น dynamic

### 7.2 การเทียบ

Normalize ทั้งสองฝั่ง: ตัด path prefix เก็บไว้แยก, lowercase, ตัดนามสกุล, แทน `-_. ` ด้วยช่องว่าง, ยุบช่องว่างซ้ำ

แยก **tag ที่มีความหมาย** ออกจากชื่อ: precision/quant (`fp8`, `fp16`, `bf16`, `e4m3fn`, `e5m2`, `q4_k_m`, `q8_0`, `nf4`, `scaled`, `gguf`),
ขนาด/รุ่น (`1.3b`, `5b`, `14b`, `xl`, `turbo`, `lightning`, `distill`), ขั้นตอน (`4step`, `8step`), และ `high_noise`/`low_noise`

คะแนน (0..1) จากลำดับนี้ หยุดที่ชั้นแรกที่เจอ
1. ตรงทุกตัวอักษร -> 1.0 (`exact`)
2. normalized ตรง -> 0.98 (`case-or-separator`)
3. ตรงหลังตัด path prefix ฝั่ง server (`wan/x.safetensors` vs `x.safetensors`) -> 0.96 (`subfolder`)
4. token set เท่ากัน tag เท่ากัน ต่างแค่ลำดับ -> 0.92 (`reordered`)
5. คำนวณ `0.6*jaccard(tokens) + 0.4*ratio(SequenceMatcher)` แล้ว **หัก 0.25 ถ้า tag ใดต่างกัน** และบันทึกว่า tag ไหนต่าง

### 7.3 นโยบาย

| ผล | เงื่อนไข | สิ่งที่เกิด |
|---|---|---|
| `ok` | คะแนน 1.0 | ผ่าน |
| `auto` | ผู้สมัครอันดับหนึ่ง ≥ 0.92, tag ไม่ต่าง, อันดับสองห่าง ≥ 0.1 | `--fix-models auto` แทนที่ให้และบันทึกใน sidecar; ถ้าไม่ใส่ flag จะ exit 3 พร้อมบอกว่าแก้ได้ด้วย flag นี้ |
| `choose` | มีผู้สมัคร ≥ 0.5 แต่ไม่เข้าเกณฑ์ auto (รวมทุกกรณีที่ tag ต่าง) | รายงาน top 3 พร้อมเหตุผลว่าต่างที่ tag ใด ต้องแก้ด้วย `--set <address>=<ชื่อเต็ม>`; ไม่มีการเดา |
| `missing` | ไม่มีผู้สมัคร ≥ 0.5 | รายงาน โฟลเดอร์ปลายทาง และถ้า template ระบุ URL ต้นทางไว้จะแนะนำคำสั่ง `download` ให้เลย |

ข้อยกเว้นที่ตั้งใจ: ไม่มี `--fix-models force` ที่เลือกอันดับหนึ่งเสมอ เพราะการสลับ fp8 กับ fp16 หรือ high_noise กับ low_noise
โดยไม่บอกทำให้ผลเพี้ยนแบบหาสาเหตุยาก ถ้า agent อยากเลือกก็ต้องระบุชื่อเต็มผ่าน `--set` ซึ่งจะถูกบันทึกไว้ใน sidecar

### 7.4 Node หายและค่าอื่น

- `class_type` ไม่มีใน object_info -> `missing_node` พร้อมชื่อ custom node pack ที่น่าจะเป็นถ้าเดาได้จาก prefix
  (เช่น `WanVideo*` -> ComfyUI-WanVideoWrapper, `VHS_*` -> VideoHelperSuite) ที่ RunPod ให้ตรวจกับ dashboard `/api/custom-nodes`
- INT/FLOAT นอก min/max, combo ค่าที่ไม่อยู่ใน options (ที่ไม่ใช่โมเดล เช่น sampler_name) -> `invalid_value` พร้อม options
- หลัง validate ฝั่ง client แล้ว ถ้า server ยังตอบ 400 จาก `/prompt` จะแปลง `node_errors` เป็นรูปแบบรายงานเดียวกัน

## 8. วงจรงานและ timeout

- `run` คืน `prompt_id` ทันทีเป็นค่าเริ่มต้น; `--wait` poll ทุก 3 วินาที (ปรับด้วย `--interval`) จนจบหรือครบ `--timeout`
  (ค่าเริ่มต้น 300 วินาที) เมื่อครบเวลา **exit 0 พร้อมสถานะ `running`** และบอกให้เรียก `wait`/`status` ต่อ ไม่ถือเป็นความล้มเหลว
- `status` รวม: อยู่ใน `queue_pending` -> `queued` (พร้อมลำดับ); อยู่ใน `queue_running` -> `running`;
  อยู่ใน `/history` -> `done` หรือ `error` (จาก `status.status_str` และ `messages` ที่มี `execution_error`)
- progress ต่อ node ถ้าต้องการใช้ WebSocket `/ws?clientId=` แบบ optional ใน `wait --progress` เท่านั้น หลุดแล้ว fallback เป็น poll
- HTTP ทุกครั้ง timeout 30 วินาที (ยกเว้น `/view` และ upload) retry 3 ครั้งแบบ exponential backoff เฉพาะ error ระดับเครือข่ายและ 502/503/504
  ซึ่งเกิดบ่อยกับ RunPod proxy ตอน ComfyUI กำลังโหลดโมเดล
- ledger: ทุก `run` บันทึก `{prompt_id, url, workflow_path, overrides, seed, submitted_at}` ลง `COMFY_STATE/runs.jsonl`
  ให้ agent ใน session ใหม่กลับมา `fetch` งานเก่าได้ตราบใดที่ pod ยังอยู่

## 9. ผลลัพธ์และ provenance

`fetch` เดินทุก node ใน `history.outputs` และดาวน์โหลดทุก entry ที่มี `filename` (`images`, `gifs`, `videos`, `audio`, และ key อื่นที่มี
`filename`+`type`) ผ่าน `/view` แบบ stream รองรับ Range เพื่อ resume

ชื่อไฟล์ปลายทาง: `<COMFY_OUT>/<YYYYMMDD-HHMMSS>-<prompt_id ย่อ 8>/<ชื่อเดิม>` และเขียน `manifest.json` ในโฟลเดอร์นั้น
ประกอบด้วย workflow ที่ส่งจริง (หลัง override), overrides, seed ที่ใช้, การแทนชื่อโมเดลที่เกิดขึ้น, url ปลายทาง, เวลา, และรายการไฟล์

ถ้า `--wait --out` ถูกใช้กับ `run` จะ fetch ให้อัตโนมัติเมื่อ `done`

## 10. ดาวน์โหลดโมเดล

- บน RunPod: เรียก dashboard `POST /download/{huggingface|civitai|googledrive}` ด้วย body `{url, model_type, api_key?, filename?}`
  ตรวจชนิดจาก host ของ URL; endpoint ตอบ 204 ทันที `--wait` จะ poll `/models/<folder>` ของ ComfyUI จนชื่อไฟล์โผล่
  (ComfyUI cache รายการโมเดล จึงส่ง `/object_info` ซ้ำครั้งหนึ่งเพื่อให้ refresh ก่อนสรุปว่ายังไม่มา)
- Local ที่ตั้ง `COMFY_MODELS_DIR`: ดาวน์โหลดตรงด้วย urllib แบบ stream ลง `<dir>/<folder>/` รองรับ `HF_TOKEN` จาก env
- ไม่เข้าเงื่อนไขทั้งสอง: exit 4 พร้อมบอก URL และโฟลเดอร์ปลายทางให้ user ทำเอง

## 11. Exit codes และรูปแบบรายงาน

| code | ความหมาย |
|---|---|
| 0 | สำเร็จ หรือ งานยังรันอยู่ (`wait` ครบเวลา) |
| 1 | ใช้คำสั่งผิด/argument ผิด |
| 2 | ต่อ ComfyUI ไม่ได้ / auth ผิด / URL ไม่ใช่ ComfyUI |
| 3 | validate ไม่ผ่าน (มีรายงาน) |
| 4 | ทำต่อไม่ได้ในสภาพแวดล้อมนี้ (เช่น download ไม่มีช่องทาง, convert เจอ subgraph) |
| 5 | งานจบด้วย error ฝั่ง ComfyUI (มี traceback ย่อจาก history) |

รายงานของ `validate` ใน `--json`:
```json
{"ok": false,
 "issues": [
  {"kind": "model_mismatch", "address": "#4.unet_name", "class": "UNETLoader", "folder": "diffusion_models",
   "wanted": "wan2.2_t2v_high_noise_14B_fp16.safetensors", "verdict": "choose",
   "candidates": [
     {"name": "wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors", "score": 0.71, "tag_diff": ["fp16->fp8","+scaled"]},
     {"name": "wan2.2_t2v_low_noise_14B_fp16.safetensors", "score": 0.66, "tag_diff": ["high_noise->low_noise"]}],
   "fix": "--set '#4.unet_name=<ชื่อเต็ม>'"},
  {"kind": "missing_node", "class": "WanVideoSampler", "hint": "ComfyUI-WanVideoWrapper"}
 ]}
```
โหมดมนุษย์พิมพ์ตารางเดียวกันแบบอ่านง่าย

## 12. เอกสาร

**SKILL.md** (ไม่เกิน 500 คำ) ประกอบด้วย
- frontmatter: `name: comfy-agent`, `description: Use when the user wants to generate or edit images/video with ComfyUI (local or RunPod), run or adapt ComfyUI workflows/templates, or when a workflow fails with missing models or nodes`
- ลำดับงานมาตรฐานเป็น numbered list: `comfy_agent.py doctor` -> เลือก workflow -> `inspect` -> `validate` -> แก้ -> `run` -> `status`/`wait` -> `fetch`
- กติกาที่ agent มักพลาด เขียนเป็น conditional บน predicate ที่สังเกตได้
  - ถ้า verdict เป็น `choose` และ tag_diff ไม่ว่าง -> ถามผู้ใช้ ไม่เลือกเอง
  - ถ้า workflow เป็นวิดีโอ (มี frames/length > 1 หรือ node VHS/Wan/LTX) -> ห้าม `--wait` เกิน 300 วินาที ให้ poll ด้วย `status`
  - ถ้า URL เป็น RunPod proxy -> เตือนผู้ใช้ให้ `fetch` ก่อน terminate
- ตารางอ้างอิงคำสั่งสั้นๆ และ pointer ไป references

**references/**
- `api.md` endpoint ที่ใช้ + response shape จริงที่ CLI พึ่งพา เพื่อให้ agent debug ได้เมื่อ CLI ไม่ครอบคลุม
- `workflows.md` วิธี export API format ใน UI ปัจจุบัน (เมนู Workflow > Export (API)), address syntax เต็ม, สิ่งที่ convert ไม่รองรับ
- `models.md` ตารางนโยบาย §7.3 พร้อมตัวอย่างการตัดสินใจ 3 กรณี (ต่างตัวพิมพ์, ต่าง precision, ต่าง variant)
- `environments.md` ตาราง local vs RunPod, ที่มาของ URL, 100 วินาที, Bash tool timeout, dashboard, terminate
- `troubleshooting.md` แผนที่ error -> คำสั่ง เช่น 502 ตอน boot, `Prompt outputs failed validation`, `Cannot execute because node X does not exist`, CUDA OOM (-> `free` หรือ ลด size), ไฟล์ input หาไม่เจอ
- `recipes.md` 4 สูตร: text-to-image, image-to-video, upscale วิดีโอ, batch จากรายการ prompt

## 13. การทดสอบ

**หน่วย (pytest, ไม่ต้องมี ComfyUI)**
- `models.py`: ตารางกรณีอย่างน้อย 20 คู่ชื่อ ครอบคลุม exact, case, subfolder, reordered, precision ต่าง, variant ต่าง, ไม่เกี่ยวกัน
  พร้อม verdict ที่คาด
- `workflow.py`: resolver ทุกแบบของ address, ชนิดค่า, ambiguity error, override ลงถูกที่
- `convert.py`: fixture UI format 3 ไฟล์ (t2i พื้นฐาน, มี bypass+reroute+primitive, มี subgraph ที่ต้อง fail) เทียบกับ API format ที่คาด
- `jobs.py`: state machine ของ status จาก fixture ของ `/queue` และ `/history`; `wait` ครบเวลาแล้ว exit 0
- `api.py`: retry เฉพาะ 502/503/504, ไม่ retry 400

**Integration (ต้องมี ComfyUI, รันเอง)**
- `tests/smoke.sh` ต่อ `COMFY_URL` จริง: doctor -> templates list -> รัน workflow ภาพเล็กสุดที่มี -> fetch -> ตรวจว่ามีไฟล์และ manifest

**ทดสอบตัว skill (ตาม superpowers:writing-skills)**
- สร้าง 3 scenario ให้ subagent ทำโดยไม่มี skill ก่อน บันทึกพฤติกรรม แล้วทำซ้ำเมื่อมี skill
  1. template ที่โมเดลต่าง precision -> คาดว่าถาม user ไม่เดา
  2. งานวิดีโอบน RunPod -> คาดว่าไม่ block ด้วย `--wait` ยาว และเตือน fetch ก่อน terminate
  3. workflow UI format ที่มี subgraph -> คาดว่าแนะนำ export API format ไม่พยายามแก้มือ

## 14. ลำดับการส่งมอบ

1. `api.py`, `jobs.py`, คำสั่ง `doctor run status wait fetch queue cancel models nodes free ledger` กับ workflow API format
   และ `--set` แบบ `#id` เท่านั้น + SKILL.md ฉบับแรก + environments.md
2. `workflow.py` เต็ม (`inspect`, address ทุกแบบ, upload อัตโนมัติ, `--seed random`) + workflows.md
3. `models.py` (`validate`, `--fix-models auto`) + `download` + models.md + troubleshooting.md
4. `templates` + `convert` + recipes.md
5. ทดสอบ skill ด้วย subagent ตาม §13 แล้วปรับ SKILL.md

แต่ละขั้นใช้งานได้จริงในตัวเอง ขั้นที่ 1 อย่างเดียวก็แทนการยิง curl ด้วยมือได้แล้ว

## 15. สมมติฐานที่ตัดสินใจไปแล้ว (แจ้งเพื่อให้ทักท้วงได้)

- ภาษา Python 3.10+ stdlib เท่านั้น ไม่ใช้ requests/httpx เพื่อให้ copy โฟลเดอร์แล้วใช้ได้ทันที
- วางไว้ใน repo นี้ที่ `skills/comfy-agent/` ไม่แยก repo เพื่อให้เวอร์ชันของ skill ไปกับ image; README ชี้วิธีติดตั้ง
- SKILL.md และ references เขียนเป็นภาษาอังกฤษ เพราะ agent อ่านได้แม่นกว่า ส่วนเอกสารออกแบบนี้เป็นภาษาไทย
- ไม่ทำ auth ในสโคปนี้ แต่ทุก request ผ่านจุดเดียวใน `api.py` เพื่อให้เพิ่ม Caddy basic auth ที่ image ทีหลังได้โดยแก้แค่ `COMFY_AUTH`
- ชื่อ endpoint ของ official templates (`/templates/index.json`, `/api/workflow_templates`) ต้องยืนยันกับ ComfyUI เวอร์ชันที่ image ใช้ตอนเริ่มขั้นที่ 4

## 16. ผลตรวจกับ ComfyUI จริง (2026-09-15, RunPod, ComfyUI 0.35.0, RTX 4090)

Stage 1 ผ่าน `tests/smoke.sh` ครบ: doctor, models, run, wait, fetch, ledger ด้วย workflow `EmptyImage -> SaveImage`
- `--set` coercion จาก `GET /object_info/{class}` ใช้ได้จริง; `/prompt` 400 ของจริงตอบ `{"error": {...}, "node_errors": {...}}` ตามที่ CLI คาด
- `/view` รองรับ Range (206) การ resume ทำงานจริง
- `GET /api/workflow_templates` คืน dict `{<custom_node_module>: [template_title, ...]}`
- `GET /templates/index.json` คืน list ของหมวด `{moduleName, category, title, templates: [{name, title, description, mediaType, mediaSubtype, tutorialUrl, ...}]}` (11 หมวดบน 0.35.0) ไฟล์ template อยู่ที่ `/templates/<name>.json` — ใช้ shape นี้ตอนทำ stage 4
