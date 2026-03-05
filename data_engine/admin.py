import os
import time
from PIL import Image
import json
import shutil
import hashlib
import requests
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, jsonify

app = Flask(__name__)

# --- 경로 설정 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_SITE_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "web_site"))

IMAGE_DIR = os.path.join(WEB_SITE_DIR, "public", "images", "characters")
TEMP_DIR = os.path.join(WEB_SITE_DIR, "public", "images", "temp")
JSON_DIR = os.path.join(WEB_SITE_DIR, "src", "content", "characters")

GIFT_IMAGE_DIR = os.path.join(WEB_SITE_DIR, "public", "images", "gifts")
GIFT_JSON_DIR = os.path.join(WEB_SITE_DIR, "src", "content", "gifts")

os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(JSON_DIR, exist_ok=True)
os.makedirs(GIFT_IMAGE_DIR, exist_ok=True)
os.makedirs(GIFT_JSON_DIR, exist_ok=True)

def get_file_hash(filepath):
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        hasher.update(f.read())
    return hasher.hexdigest()

# ==========================================
# 0-1. 나무위키 파서 (인격용)
# ==========================================
def parse_namuwiki_text(raw_text):
    data = {"skills": {}, "defense": {}, "specialDefense": {}, "affiliation": []}
    clean_text = re.sub(r'\[\d+\]', '', raw_text)
    
    name_match = re.search(r'\[\s*(.+?)\s*\]\s*([^\n]+)', clean_text)
    if name_match:
        data['identityName'] = name_match.group(1).strip()
        data['characterName'] = re.sub(r'["\'].*', '', name_match.group(2)).strip()
        
    star_count = clean_text.count('★')
    if star_count > 0: data['grade'] = min(star_count, 3)
    else:
        grade_match = re.search(r'(\d)\s*성', clean_text)
        data['grade'] = int(grade_match.group(1)) if grade_match else 1
            
    release_match = re.search(r'출시 시기\s*([\d\.]+)', clean_text)
    if release_match: data['releaseDate'] = release_match.group(1).replace('.', '-').strip('-')
        
    affiliation_match = re.search(r'특성\s*키워드\s*([^\n]+)', clean_text)
    if affiliation_match:
        aff_str = affiliation_match.group(1).split('인격')[0].strip()
        data['affiliation'] = [a.strip() for a in aff_str.split(',') if a.strip()]
        
    skills = re.findall(r'공격 유형.{0,20}?(참격|관통|타격).{0,20}?죄악 속성.{0,20}?(분노|색욕|나태|탐식|우울|오만|질투|없음)', clean_text, re.DOTALL)
    for i in range(3):
        if i < len(skills): data['skills'][f'skill{i+1}'] = {"type": skills[i][0], "attribute": skills[i][1]}
    for i in range(3, 6):
        if i < len(skills): data['skills'][f'special{i-2}'] = {"type": skills[i][0], "attribute": skills[i][1]}
        
    defense_matches = re.findall(r'수비 유형.{0,20}?(가드|방어|수비|회피|반격|강화\s*가드|강화\s*방어|강화\s*수비|강화\s*회피|강화\s*반격).{0,20}?죄악 속성.{0,20}?(분노|색욕|나태|탐식|우울|오만|질투|없음)', clean_text, re.DOTALL)
    if len(defense_matches) > 0:
        dt1 = defense_matches[0][0].replace(" ", "")
        if dt1 in ["방어", "수비"]: dt1 = "가드"
        elif dt1 in ["강화가드", "강화수비"]: dt1 = "강화방어"
        data['defense'] = {"type": dt1, "attribute": defense_matches[0][1]}
    if len(defense_matches) > 1:
        dt2 = defense_matches[1][0].replace(" ", "")
        if dt2 in ["방어", "수비"]: dt2 = "가드"
        elif dt2 in ["강화가드", "강화수비"]: dt2 = "강화방어"
        data['specialDefense'] = {"type": dt2, "attribute": defense_matches[1][1]}

    return data

# ==========================================
# 0-2. 나무위키 파서 (기프트 전용)
# ==========================================
def parse_gift_namuwiki_text(raw_text):
    data = {"name": "", "tier": 1, "category": "범용", "materials": [], "special_keywords": [], "effect": "", "resonance_condition": "", "identity_condition": "", "target_condition": []}
    
    clean_text = raw_text.replace('\xa0', ' ').replace('\u200b', '')
    lines = [line.strip() for line in clean_text.split('\n') if line.strip()]
    if not lines: return data
        
    first_line = lines[0]
    raw_name = re.sub(r'^[ⅠⅡⅢⅣⅤ]\s*', '', first_line)
    data['name'] = re.sub(r'\[.*?\]', '', raw_name).strip()
        
    valid_categories = ['참격', '관통', '타격', '화상', '출혈', '진동', '파열', '침잠', '호흡', '충전', '범용']
    if len(lines) > 1:
        cat_candidate = re.sub(r'\[.*?\]', '', lines[1]).strip()
        for vc in valid_categories:
            if vc in cat_candidate:
                data['category'] = vc
                break
        
    effect_idx = -1
    for i, line in enumerate(lines):
        if line == '등급' and i + 1 < len(lines) and lines[i+1].isdigit():
            data['tier'] = int(lines[i+1])
            
        if line.startswith('조합식') and i + 1 < len(lines):
            mat_line = lines[i+1]
            mats = [m.strip() for m in mat_line.split('+')]
            cleaned_mats = [re.sub(r'중 택.*', '', m).strip() for m in mats]
            data['materials'] = cleaned_mats
            
        if line == '효과':
            effect_idx = i
            break
            
    if effect_idx != -1:
        data['effect'] = '\n'.join(lines[effect_idx+1:])
        
    return data

@app.route('/api/parse_gift_text', methods=['POST'])
def api_parse_gift_text():
    raw_text = request.form.get('raw_text', '').strip()
    if raw_text: return jsonify({"status": "success", "data": parse_gift_namuwiki_text(raw_text)})
    return jsonify({"status": "error", "message": "텍스트를 입력해주세요."})

# ==========================================
# 1. 라우터
# ==========================================
@app.route('/images/<filename>')
def serve_image(filename): return send_from_directory(IMAGE_DIR, filename)

@app.route('/temp_images/<filename>')
def serve_temp_image(filename): return send_from_directory(TEMP_DIR, filename)

@app.route('/gifts/<filename>')
def serve_gift_image(filename): return send_from_directory(GIFT_IMAGE_DIR, filename)

@app.route('/api/parse_text', methods=['POST'])
def api_parse_text():
    raw_text = request.form.get('raw_text', '').strip()
    if raw_text: return jsonify({"status": "success", "data": parse_namuwiki_text(raw_text)})
    return jsonify({"status": "error", "message": "텍스트를 입력해주세요."})

# ==========================================
# 2. [인격] 도감 데이터 팩토리
# ==========================================
@app.route('/')
def index():
    valid_extensions = ('.png', '.jpg', '.jpeg', '.webp')
    all_images = sorted([f for f in os.listdir(IMAGE_DIR) if f.lower().endswith(valid_extensions)])
    image_data_list = []
    for img in all_images:
        char_id = os.path.splitext(img)[0]
        json_path = os.path.join(JSON_DIR, f"{char_id}.json")
        has_data = os.path.exists(json_path)
        existing_data = {}
        display_name = ""
        if has_data:
            with open(json_path, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
                display_name = f"[{existing_data.get('identityName', '이름없음')}] {existing_data.get('characterName', '')}"
        image_data_list.append({"filename": img, "char_id": char_id, "has_data": has_data, "display_name": display_name, "json_data": existing_data})
    return render_template('index.html', images=image_data_list)

@app.route('/save', methods=['POST'])
def save():
    old_char_id = request.form['char_id']
    img_filename = request.form['img_filename']
    identityName = request.form['identityName'].strip()
    characterName = request.form['characterName'].strip()

    safe_identity = re.sub(r'[\\/*?:"<>|]', "", identityName).replace(" ", "_")
    safe_character = re.sub(r'[\\/*?:"<>|]', "", characterName).replace(" ", "_")
    new_char_id = f"{safe_identity}_{safe_character}_{int(time.time())}"

    old_img_path = os.path.join(IMAGE_DIR, img_filename)
    new_img_filename = f"{new_char_id}.webp"
    new_img_path = os.path.join(IMAGE_DIR, new_img_filename)

    if os.path.exists(old_img_path):
        try:
            img = Image.open(old_img_path)
            img.save(new_img_path, 'webp', quality=85)
            if old_img_path != new_img_path: os.remove(old_img_path)
        except:
            ext = os.path.splitext(img_filename)[1]
            new_img_filename = f"{new_char_id}{ext}"
            new_img_path = os.path.join(IMAGE_DIR, new_img_filename)
            if old_img_path != new_img_path: shutil.move(old_img_path, new_img_path)
    else: new_img_filename = img_filename

    old_json_path = os.path.join(JSON_DIR, f"{old_char_id}.json")
    new_json_path = os.path.join(JSON_DIR, f"{new_char_id}.json")
    if old_char_id != new_char_id and os.path.exists(old_json_path): os.remove(old_json_path)

    affiliation_list = [a.strip() for a in request.form['affiliation'].split(',') if a.strip()]
    checked_keywords = request.form.getlist('keywords_check')
    manual_keywords = [k.strip() for k in request.form.get('manual_keywords', '').split(',') if k.strip()]
    final_keywords = list(set(checked_keywords + manual_keywords))
    
    character_data = {
        "id": new_char_id, "characterName": characterName, "identityName": identityName,
        "isDefault": request.form.get('isDefault') == 'on', "grade": int(request.form['grade']),
        "releaseDate": request.form['releaseDate'], "imagePosition": request.form.get('imagePosition', 'center'),
        "keywords": final_keywords,
        "skills": {
            "skill1": {"type": request.form['skill1_type'], "attribute": request.form['skill1_attr']},
            "skill2": {"type": request.form['skill2_type'], "attribute": request.form['skill2_attr']},
            "skill3": {"type": request.form['skill3_type'], "attribute": request.form['skill3_attr']},
            "special1": {"type": request.form['special1_type'], "attribute": request.form['special1_attr']},
            "special2": {"type": request.form['special2_type'], "attribute": request.form['special2_attr']},
            "special3": {"type": request.form['special3_type'], "attribute": request.form['special3_attr']},
        },
        "defense": {"type": request.form.get('defense_type', '가드'), "attribute": request.form.get('defense_attr', '없음')},
        "specialDefense": {"type": request.form.get('sp_def_type', '없음'), "attribute": request.form.get('sp_def_attr', '없음')},
        "affiliation": affiliation_list if affiliation_list else ["림버스 컴퍼니"],
        "image_url": f"/images/characters/{new_img_filename}?v={int(time.time())}"
    }
    with open(new_json_path, 'w', encoding='utf-8') as f: json.dump(character_data, f, ensure_ascii=False, indent=2)
    return redirect(url_for('index'))

@app.route('/delete', methods=['POST'])
def delete_image():
    img_filename = request.form['img_filename']
    char_id = request.form['char_id']
    if os.path.exists(os.path.join(IMAGE_DIR, img_filename)): os.remove(os.path.join(IMAGE_DIR, img_filename))
    if os.path.exists(os.path.join(JSON_DIR, f"{char_id}.json")): os.remove(os.path.join(JSON_DIR, f"{char_id}.json"))
    return redirect(url_for('index'))

@app.route('/batch_convert', methods=['POST'])
def batch_convert():
    converted_count = 0
    for idx, j_file in enumerate(os.listdir(JSON_DIR)):
        if not j_file.endswith('.json'): continue
        old_char_id = os.path.splitext(j_file)[0]
        old_json_path = os.path.join(JSON_DIR, j_file)
        with open(old_json_path, 'r', encoding='utf-8') as f: data = json.load(f)
        safe_id = re.sub(r'[\\/*?:"<>|]', "", data.get('identityName', 'Unknown')).replace(" ", "_")
        safe_char = re.sub(r'[\\/*?:"<>|]', "", data.get('characterName', 'Unknown')).replace(" ", "_")
        if safe_id in old_char_id and safe_char in old_char_id: continue
        timestamp = int(time.time()) + idx 
        new_char_id = f"{safe_id}_{safe_char}_{timestamp}"
        old_img_filename = None
        for ext in ['.webp', '.png', '.jpg', '.jpeg']:
            if os.path.exists(os.path.join(IMAGE_DIR, f"{old_char_id}{ext}")):
                old_img_filename = f"{old_char_id}{ext}"; break
        if not old_img_filename: continue
        old_img_path = os.path.join(IMAGE_DIR, old_img_filename)
        new_img_filename = f"{new_char_id}.webp"
        new_img_path = os.path.join(IMAGE_DIR, new_img_filename)
        try:
            img = Image.open(old_img_path)
            img.save(new_img_path, 'webp', quality=85)
            if old_img_path != new_img_path: os.remove(old_img_path)
        except:
            ext = os.path.splitext(old_img_filename)[1]
            new_img_filename = f"{new_char_id}{ext}"
            new_img_path = os.path.join(IMAGE_DIR, new_img_filename)
            shutil.move(old_img_path, new_img_path)
        data['id'] = new_char_id
        data['image_url'] = f"/images/characters/{new_img_filename}?v={timestamp}"
        with open(os.path.join(JSON_DIR, f"{new_char_id}.json"), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.remove(old_json_path)
        converted_count += 1
    return jsonify({"status": "success", "message": f"🎉 총 {converted_count}개의 데이터 일괄 변경 완료!"})

# ==========================================
# 3. 🎁 기프트 데이터 팩토리
# ==========================================
@app.route('/gift_factory')
def gift_factory_ui():
    valid_extensions = ('.png', '.jpg', '.jpeg', '.webp')
    all_images = sorted([f for f in os.listdir(GIFT_IMAGE_DIR) if f.lower().endswith(valid_extensions)])
    
    gift_data_list = []
    for img in all_images:
        gift_id = os.path.splitext(img)[0]
        json_path = os.path.join(GIFT_JSON_DIR, f"{gift_id}.json")
        has_data = os.path.exists(json_path)
        existing_data = {}
        display_name = ""
        if has_data:
            with open(json_path, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
                display_name = existing_data.get('name', '이름없음')
        gift_data_list.append({"filename": img, "gift_id": gift_id, "has_data": has_data, "display_name": display_name, "json_data": existing_data})

    unique_affiliations = set()
    unique_keywords = set()
    common_kws = ['화상', '출혈', '진동', '파열', '침잠', '호흡', '충전']

    if os.path.exists(JSON_DIR):
        for f_name in os.listdir(JSON_DIR):
            if f_name.endswith('.json'):
                try:
                    with open(os.path.join(JSON_DIR, f_name), 'r', encoding='utf-8') as f:
                        c_data = json.load(f)
                        for aff in c_data.get('affiliation', []):
                            if aff.strip(): unique_affiliations.add(aff.strip())
                        for kw in c_data.get('keywords', []):
                            if kw.strip() and kw.strip() not in common_kws:
                                unique_keywords.add(kw.strip())
                except: pass

    existing_gift_names = set()
    if os.path.exists(GIFT_JSON_DIR):
        for f_name in os.listdir(GIFT_JSON_DIR):
            if f_name.endswith('.json'):
                try:
                    with open(os.path.join(GIFT_JSON_DIR, f_name), 'r', encoding='utf-8') as f:
                        g_data = json.load(f)
                        if g_data.get('name'):
                            existing_gift_names.add(g_data['name'].strip())
                except: pass

    return render_template('gift_factory.html', images=gift_data_list, rec_affiliations=sorted(list(unique_affiliations)), rec_keywords=sorted(list(unique_keywords)), rec_gifts=sorted(list(existing_gift_names)))

@app.route('/save_gift', methods=['POST'])
def save_gift():
    old_gift_id = request.form['gift_id']
    img_filename = request.form['img_filename']
    gift_name = request.form['name'].strip()
    
    safe_name = re.sub(r'[\\/*?:"<>|]', "", gift_name).replace(" ", "_")
    timestamp = int(time.time())
    new_gift_id = f"gift_{safe_name}_{timestamp}"
    
    old_img_path = os.path.join(GIFT_IMAGE_DIR, img_filename)
    new_img_filename = f"{new_gift_id}.webp"
    new_img_path = os.path.join(GIFT_IMAGE_DIR, new_img_filename)

    if os.path.exists(old_img_path):
        try:
            img = Image.open(old_img_path)
            img.save(new_img_path, 'webp', quality=85)
            if old_img_path != new_img_path: os.remove(old_img_path)
        except Exception:
            ext = os.path.splitext(img_filename)[1]
            new_img_filename = f"{new_gift_id}{ext}"
            new_img_path = os.path.join(GIFT_IMAGE_DIR, new_img_filename)
            shutil.move(old_img_path, new_img_path)

    old_json_path = os.path.join(GIFT_JSON_DIR, f"{old_gift_id}.json")
    if old_gift_id != new_gift_id and os.path.exists(old_json_path):
        os.remove(old_json_path)

    id_cond_list = [k.strip() for k in request.form.get('identity_condition', '').split(',') if k.strip()]
    target_cond_list = [k.strip() for k in request.form.get('target_condition', '').split(',') if k.strip()] # 🚀 신규 추가
    sp_kw_list = [k.strip() for k in request.form.get('special_keywords', '').split(',') if k.strip()]
    materials_list = [m.strip() for m in request.form.get('materials', '').split(',') if m.strip()]

    is_ego = request.form.get('is_ego_gift') == 'on'

    gift_data = {
        "id": new_gift_id,
        "name": gift_name,
        "tier": int(request.form.get('tier', 1)),
        "category": request.form.get('category', '범용'),
        "special_keywords": sp_kw_list,
        "materials": materials_list,
        "resonance_condition": request.form.get('resonance_condition', '').strip(), 
        "identity_condition": id_cond_list,
        "target_condition": target_cond_list, # 🚀 적용 대상 및 편성 순서 추가
        "condition_dependency": request.form.get('condition_dependency', 'none'),
        "is_ego_gift": is_ego,
        "effect": request.form.get('effect', '').strip(),
        "image_url": f"/images/gifts/{new_img_filename}?v={timestamp}"
    }
    
    new_json_path = os.path.join(GIFT_JSON_DIR, f"{new_gift_id}.json")
    with open(new_json_path, 'w', encoding='utf-8') as f:
        json.dump(gift_data, f, ensure_ascii=False, indent=2)
        
    return redirect(url_for('gift_factory_ui'))

@app.route('/delete_gift', methods=['POST'])
def delete_gift():
    img_filename = request.form['img_filename']
    gift_id = request.form['gift_id']
    if os.path.exists(os.path.join(GIFT_IMAGE_DIR, img_filename)): os.remove(os.path.join(GIFT_IMAGE_DIR, img_filename))
    if os.path.exists(os.path.join(GIFT_JSON_DIR, f"{gift_id}.json")): os.remove(os.path.join(GIFT_JSON_DIR, f"{gift_id}.json"))
    return redirect(url_for('gift_factory_ui'))

# ==========================================
# 4. 스테이징 크롤러
# ==========================================
@app.route('/scraper')
def scraper_ui(): return render_template('scraper.html')

@app.route('/run_scraper', methods=['POST'])
def run_scraper():
    target_url = request.form['url']
    prefix = request.form.get('prefix', '').strip() or "auto_img"
    headers = {'User-Agent': 'Mozilla/5.0'}
    for f in os.listdir(TEMP_DIR): os.remove(os.path.join(TEMP_DIR, f))
    existing_hashes = {get_file_hash(os.path.join(IMAGE_DIR, f)): f for f in os.listdir(IMAGE_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))}
    scraped_files, duplicated_files = [], []
    try:
        soup = BeautifulSoup(requests.get(target_url, headers=headers, timeout=10).text, 'html.parser')
        for idx, img in enumerate(soup.find_all('img')):
            img_url = urljoin(target_url, img.get('src') or img.get('data-src'))
            if not img_url or img_url.endswith(('.gif', '.svg')) or 'icon' in img_url.lower() or 'logo' in img_url.lower(): continue
            try:
                img_data = requests.get(img_url, headers=headers, timeout=5).content
                if len(img_data) < 10240: continue
                filename = f"{prefix}_{int(time.time())}_{idx}.jpg"
                filepath = os.path.join(TEMP_DIR, filename)
                with open(filepath, 'wb') as f: f.write(img_data)
                new_hash = get_file_hash(filepath)
                if new_hash in existing_hashes: duplicated_files.append({'temp_name': filename, 'original_name': existing_hashes[new_hash]})
                else: scraped_files.append(filename)
            except: pass 
        return render_template('select_images.html', images=scraped_files, duplicates=duplicated_files, target_url=target_url)
    except Exception as e: return f"<h1 style='color:red;'>오류</h1><p>{str(e)}</p><a href='/scraper'>돌아가기</a>"

@app.route('/save_selected_images', methods=['POST'])
def save_selected_images():
    for filename in request.form.getlist('selected_images'):
        if os.path.exists(os.path.join(TEMP_DIR, filename)): shutil.move(os.path.join(TEMP_DIR, filename), os.path.join(IMAGE_DIR, filename))
    for f in os.listdir(TEMP_DIR): os.remove(os.path.join(TEMP_DIR, f))
    return redirect(url_for('index'))
    
@app.route('/cleanup')
def cleanup_orphans():
    valid_ids = [os.path.splitext(f)[0] for f in os.listdir(IMAGE_DIR) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
    for j_file in os.listdir(JSON_DIR):
        if j_file.endswith('.json') and os.path.splitext(j_file)[0] not in valid_ids: os.remove(os.path.join(JSON_DIR, j_file))
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)