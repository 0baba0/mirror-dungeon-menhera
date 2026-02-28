import os
import json
import time
import shutil
import hashlib
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from flask import Flask, render_template, request, redirect, url_for, send_from_directory

app = Flask(__name__)

# --- 경로 설정 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_SITE_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "web_site"))
IMAGE_DIR = os.path.join(WEB_SITE_DIR, "public", "images", "characters")
TEMP_DIR = os.path.join(WEB_SITE_DIR, "public", "images", "temp")
JSON_DIR = os.path.join(WEB_SITE_DIR, "src", "content", "characters")

os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(JSON_DIR, exist_ok=True)

# 파일 지문(MD5 Hash) 추출 헬퍼 함수
def get_file_hash(filepath):
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        hasher.update(f.read())
    return hasher.hexdigest()

# ==========================================
# 1. 공통 이미지 서빙 라우터
# ==========================================
@app.route('/images/<filename>')
def serve_image(filename):
    return send_from_directory(IMAGE_DIR, filename)

@app.route('/temp_images/<filename>')
def serve_temp_image(filename):
    return send_from_directory(TEMP_DIR, filename)

# ==========================================
# 2. 도감 데이터 팩토리 (메인 화면)
# ==========================================
@app.route('/')
def index():
    images = sorted([f for f in os.listdir(IMAGE_DIR) if f.lower().endswith(('.png', '.jpg', '.jpeg'))])
    
    # URL에 page 번호가 없을 때 (스마트 이어하기)
    if 'page' not in request.args:
        target_page = len(images) 
        for i, img in enumerate(images):
            char_id = os.path.splitext(img)[0]
            if not os.path.exists(os.path.join(JSON_DIR, f"{char_id}.json")):
                target_page = i
                break
        return redirect(url_for('index', page=target_page))

    # 🚀 빈칸이나 이상한 문자가 들어오면 무조건 0(처음)으로 처리하는 방어 로직
    page_str = request.args.get('page', '0')
    page = int(page_str) if page_str.isdigit() else 0
    if page < 0: page = 0
    
    # 🚀 신규: 드롭다운 검색을 위한 전체 데이터 목록 생성
    search_list = []
    for i, img in enumerate(images):
        char_id = os.path.splitext(img)[0]
        json_path = os.path.join(JSON_DIR, f"{char_id}.json")
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                j_data = json.load(f)
                display_name = f"[{j_data.get('identityName', '이름없음')}] {j_data.get('characterName', '')}"
        else:
            display_name = "(미입력 데이터)"
        search_list.append({"page": i, "name": display_name})

    # 모든 작업 완료 시
    if page >= len(images):
        return f"""
        <div style="font-family:sans-serif; background:#121212; color:#fff; padding:3rem; text-align:center;">
            <h1 style="color:#eab308;">🎉 총 {len(images)}개의 데이터 작업이 모두 끝났습니다!</h1>
            <p>빈틈없이 완벽하게 도감이 채워졌습니다.</p>
            <br>
            <a href="/?page=0" style="color:#fff; text-decoration:none; padding:1rem; background:#444; border-radius:4px; margin-right:1rem;">1번부터 다시 검토하기</a>
            <a href="/scraper" style="color:#000; text-decoration:none; padding:1rem; background:#eab308; border-radius:4px;">새 이미지 수집하러 가기 ➔</a>
        </div>
        """
        
    current_image = images[page]
    char_id = os.path.splitext(current_image)[0]
    
    json_path = os.path.join(JSON_DIR, f"{char_id}.json")
    existing_data = {}
    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
            
    # search_list를 화면으로 같이 넘겨줍니다
    return render_template('index.html', image=current_image, char_id=char_id, page=page, total=len(images), data=existing_data, search_list=search_list)

@app.route('/save', methods=['POST'])
def save():
    char_id = request.form['char_id']
    page = int(request.form['page'])
    img_filename = request.form['img_filename']
    
    affiliation_list = [a.strip() for a in request.form['affiliation'].split(',') if a.strip()]
    checked_keywords = request.form.getlist('keywords_check')
    manual_keywords_str = request.form.get('manual_keywords', '')
    manual_keywords = [k.strip() for k in manual_keywords_str.split(',') if k.strip()]
    final_keywords = list(set(checked_keywords + manual_keywords))
    
    character_data = {
        "id": char_id,
        "characterName": request.form['characterName'],
        "identityName": request.form['identityName'],
        "isDefault": request.form.get('isDefault') == 'on',
        "grade": int(request.form['grade']),
        "releaseDate": request.form['releaseDate'],
        "imagePosition": request.form.get('imagePosition', 'center'),
        "keywords": final_keywords,
        "skills": {
            "skill1": {"type": request.form['skill1_type'], "attribute": request.form['skill1_attr']},
            "skill2": {"type": request.form['skill2_type'], "attribute": request.form['skill2_attr']},
            "skill3": {"type": request.form['skill3_type'], "attribute": request.form['skill3_attr']},
            "special1": {"type": request.form['special1_type'], "attribute": request.form['special1_attr']},
            "special2": {"type": request.form['special2_type'], "attribute": request.form['special2_attr']},
            "special3": {"type": request.form['special3_type'], "attribute": request.form['special3_attr']},
        },
        "defense": {"type": request.form['defense_type'], "attribute": request.form['defense_attr']},
        "affiliation": affiliation_list if affiliation_list else ["림버스 컴퍼니"],
        "image_url": f"/images/characters/{img_filename}"
    }
    
    json_path = os.path.join(JSON_DIR, f"{char_id}.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(character_data, f, ensure_ascii=False, indent=2)
        
    return redirect(url_for('index', page=page+1))

@app.route('/delete', methods=['POST'])
def delete_image():
    # 현재 이미지와 관련 JSON 파일을 완전히 삭제하는 기능
    img_filename = request.form['img_filename']
    char_id = request.form['char_id']
    page = int(request.form['page'])
    
    img_path = os.path.join(IMAGE_DIR, img_filename)
    json_path = os.path.join(JSON_DIR, f"{char_id}.json")
    
    if os.path.exists(img_path): os.remove(img_path)
    if os.path.exists(json_path): os.remove(json_path)
    
    # 이미지가 삭제되면 뒤에 있던 이미지가 현재 인덱스(page)로 당겨오므로 같은 page로 리다이렉트
    return redirect(url_for('index', page=page))


# ==========================================
# 3. 스테이징 크롤러 (이미지 수집기)
# ==========================================
@app.route('/scraper')
def scraper_ui():
    return render_template('scraper.html')

@app.route('/run_scraper', methods=['POST'])
def run_scraper():
    target_url = request.form['url']
    prefix = request.form.get('prefix', '').strip()
    if not prefix:
        prefix = "auto_img"
        
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    # 임시 폴더 비우기
    for f in os.listdir(TEMP_DIR):
        os.remove(os.path.join(TEMP_DIR, f))
        
    # 기존 본진 이미지 해시(지문) 매핑 저장
    existing_hashes = {}
    for f in os.listdir(IMAGE_DIR):
        if f.lower().endswith(('.jpg', '.jpeg', '.png')):
            existing_hashes[get_file_hash(os.path.join(IMAGE_DIR, f))] = f
            
    scraped_files = []
    duplicated_files = [] # 중복 파일 목록
    
    try:
        response = requests.get(target_url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        img_tags = soup.find_all('img')
        
        for idx, img in enumerate(img_tags):
            img_url = img.get('src') or img.get('data-src')
            if not img_url: continue
            img_url = urljoin(target_url, img_url)
            
            # 1차 필터링
            if img_url.endswith(('.gif', '.svg')) or 'icon' in img_url.lower() or 'logo' in img_url.lower():
                continue

            try:
                img_data = requests.get(img_url, headers=headers, timeout=5).content
                if len(img_data) < 10240: 
                    continue
                    
                filename = f"{prefix}_{int(time.time())}_{idx}.jpg"
                filepath = os.path.join(TEMP_DIR, filename)
                
                with open(filepath, 'wb') as f:
                    f.write(img_data)
                    
                # 3차 필터링: 중복 검사
                new_hash = get_file_hash(filepath)
                if new_hash in existing_hashes:
                    # 중복인 경우 화면에 보여주기 위해 정보 추가
                    duplicated_files.append({
                        'temp_name': filename,
                        'original_name': existing_hashes[new_hash]
                    })
                else:
                    scraped_files.append(filename)
                    
            except Exception:
                pass 
                
        return render_template('select_images.html', images=scraped_files, duplicates=duplicated_files, target_url=target_url)
        
    except Exception as e:
        return f"<h1 style='color:red;'>오류 발생</h1><p>{str(e)}</p><a href='/scraper'>돌아가기</a>"

@app.route('/save_selected_images', methods=['POST'])
def save_selected_images():
    selected_images = request.form.getlist('selected_images')
    saved_count = 0
    
    for filename in selected_images:
        temp_path = os.path.join(TEMP_DIR, filename)
        final_path = os.path.join(IMAGE_DIR, filename)
        
        if os.path.exists(temp_path):
            shutil.move(temp_path, final_path)
            saved_count += 1
            
    for f in os.listdir(TEMP_DIR):
        os.remove(os.path.join(TEMP_DIR, f))
        
    return f"""
    <div style="font-family:sans-serif; background:#121212; color:#fff; padding:3rem; text-align:center;">
        <h1 style="color:#eab308;">✅ {saved_count}개의 이미지 최종 저장 완료!</h1>
        <p>선택하지 않은 찌꺼기 파일들은 완벽하게 삭제되었습니다.</p>
        <br>
        <a href="/scraper" style="color:#fff; text-decoration:none; padding:1rem; background:#444; border-radius:4px; margin-right:1rem;">다른 사이트 더 긁어오기</a>
        <a href="/" style="color:#000; text-decoration:none; padding:1rem; background:#eab308; border-radius:4px;">도감 데이터 입력하러 가기 ➔</a>
    </div>
    """
    
@app.route('/cleanup')
def cleanup_orphans():
    # 1. 현재 존재하는 진짜 이미지들의 ID(이름) 목록을 가져옵니다.
    valid_ids = [os.path.splitext(f)[0] for f in os.listdir(IMAGE_DIR) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    
    cleaned_count = 0
    # 2. JSON 폴더를 싹 뒤집니다.
    for j_file in os.listdir(JSON_DIR):
        if j_file.endswith('.json'):
            char_id = os.path.splitext(j_file)[0]
            # 3. 만약 JSON 이름이 진짜 이미지 목록에 없다면? -> 고아 데이터이므로 삭제!
            if char_id not in valid_ids:
                os.remove(os.path.join(JSON_DIR, j_file))
                cleaned_count += 1
                
    return f"""
    <div style="font-family:sans-serif; background:#121212; color:#fff; padding:3rem; text-align:center;">
        <h1 style="color:#eab308;">🧹 데이터 검수 및 청소 완료!</h1>
        <p>이미지가 없어서 버려진 '주인 잃은 JSON 데이터' <b>{cleaned_count}개</b>를 완벽하게 삭제했습니다.</p>
        <br>
        <a href="/" style="color:#000; text-decoration:none; padding:1rem; background:#eab308; border-radius:4px;">메인으로 돌아가기 ➔</a>
    </div>
    """

if __name__ == '__main__':
    print("🚀 로컬 데이터 관리자 서버가 켜졌습니다! http://localhost:5000 으로 접속하세요.")
    app.run(debug=True, port=5000)