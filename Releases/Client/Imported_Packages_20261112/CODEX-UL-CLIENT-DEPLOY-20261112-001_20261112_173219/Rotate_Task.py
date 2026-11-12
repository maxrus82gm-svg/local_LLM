import hashlib,json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REPO=Path(r'M:\GitHub\local_LLM')
TASK='CODEX-UL-CLIENT-DEPLOY-20261112-001'
PREVIOUS='CODEX-UL-STREAM-SLOTS-20261112-001'
ARCHIVE='9900ccd27ce60f713146da3b9037c99b68bfb2b2'
path=REPO/'Documents/07_Задачи Codex.md'
raw=path.read_bytes();bom=b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b''
text=raw[len(bom):].decode('utf-8');nl='\r\n' if '\r\n' in text else '\n'
headers=list(re.finditer(r'^### БЛОК .+$',text,re.M));assert len(headers)==5
positions=[h.start() for h in headers]+[len(text)]
sections=[text[positions[i]:positions[i+1]] for i in range(5)]
assert '# '+TASK+nl in sections[0] and '# '+PREVIOUS+nl in sections[1]
def body(section,task):return section[section.index('# '+task):].strip().replace('\r\n','\n')
archived=subprocess.check_output(['git','show',ARCHIVE+':Documents/07_Задачи Codex.md'],cwd=REPO).decode('utf-8-sig').replace('\r\n','\n')
archived_body=archived[archived.index('# '+PREVIOUS):]
next_heading=re.search(r'^### БЛОК ',archived_body,re.M)
if next_heading:archived_body=archived_body[:next_heading.start()]
assert body(sections[1],PREVIOUS)==archived_body.strip()
assert PREVIOUS in (REPO/'Documents/05_Реестр_задач.md').read_text(encoding='utf-8-sig')
assert ARCHIVE in (REPO/'Documents/09_История_задач.md').read_text(encoding='utf-8-sig')
assert (ROOT/'REPORT.txt').is_file() and (ROOT/'EVIDENCE.json').is_file()
original_task=sections[0][sections[0].index('# '+TASK):]
new_one=headers[0].group().rstrip('\r')+nl+nl+'Свободен. Последняя сданная задача — БЛОК 1.1; независимая приёмка ожидается.'+nl+nl
new_submitted=headers[1].group().rstrip('\r')+nl+nl+'**'+TASK+' — SUBMITTED / REVIEW PENDING.** 12.11.2026. CLIENT DEPLOY PASS / MANAGER VERSION GATE. Полный дословный оригинал ниже.'+nl+nl+original_task
bullets=[line for line in sections[2].splitlines() if line.startswith('- **')]
assert len(bullets)==5
latest='- **'+TASK+' / 12.11:** установлен Client R5 из source 132474781e760e463944c76efcd9d3ff192e8f18 в M:\\UltraLLM_Client старым ярлыком; R4 backup 70/70, release 72/72 и install 73/73 SHA256, 49 Client и SOURCE/frozen Chrome P0/P1 PASS; 34 сообщения сохранены, настоящий Manager ONLINE. CLIENT DEPLOY PASS / MANAGER VERSION GATE; independent REVIEW PENDING. Полный отчёт: '+str(ROOT/'REPORT.txt')+'; evidence: '+str(ROOT/'EVIDENCE.json')+'.'
new_index=headers[2].group().rstrip('\r')+nl+nl+nl.join([latest,*bullets[:4]])+nl+nl+'Здесь только 5 последних ID. Полные исходники и архив — №09, immutable Git commit и №05 индекс.'+nl+nl
open_lines=sections[3].splitlines()
open_lines=[line for line in open_lines if not line.startswith('- Реальная Colibri1/Qwen3.6 скорость')]
new_open=headers[3].group().rstrip('\r')+nl+nl+'- Client R5 установлен и открыт старым ярлыком; Manager прежней версии. Реальные streaming/reasoning, dynamic slots, Colibri1 direct/routed benchmark и START/STOP — NOT RUN / отдельный OWNER GO. SECOND PC NOT RUN.'+nl
new_open+=nl.join(open_lines[2:]).rstrip()+nl+nl
updated=text[:positions[0]]+new_one+new_submitted+new_index+new_open+sections[4]
assert updated[updated.index(headers[4].group().rstrip('\r')):]==sections[4]
after_sections=list(re.finditer(r'^### БЛОК .+$',updated,re.M))
new_task_section=updated[after_sections[1].start():after_sections[2].start()]
assert body(new_task_section,TASK)==body(sections[0],TASK)
assert path.read_bytes()==raw,'Concurrent document edit; refuse overwrite'
result_bytes=bom+updated.encode('utf-8');path.write_bytes(result_bytes)
assert path.read_bytes()==result_bytes
result={'task_id':TASK,'status':'SUBMITTED / REVIEW PENDING','block1':'FREE','block1_1':'EXACT TASK ORIGINAL',
    'previous_archive_git_sha':ARCHIVE,'previous_archive_registered_05_09':True,
    'previous_task_sha256':hashlib.sha256(archived_body.strip().encode()).hexdigest(),
    'current_task_sha256':hashlib.sha256(body(sections[0],TASK).encode()).hexdigest(),
    'block4_byte_unchanged':True,'block4_sha256':hashlib.sha256(sections[4].encode()).hexdigest(),
    'document_before_sha256':hashlib.sha256(raw).hexdigest(),'document_after_sha256':hashlib.sha256(result_bytes).hexdigest(),
    'document':str(path),'short_index_entries':5,'git_commit_push':'NOT RUN'}
(ROOT/'ROTATION.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
