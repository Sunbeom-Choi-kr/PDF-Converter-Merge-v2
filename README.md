# PDF-Converter-Merge-v2

PDF Converter & Merger (MVP) — PRD v1.0 기반 원페이지 웹 애플리케이션입니다.

## 포함 기능
- 드래그 앤 드롭 / 클릭 업로드
- 파일 목록 표시 및 순서 재정렬 (모바일은 ↑ ↓ 버튼)
- 변환 진행 상태 표시 (SSE 스트리밍)
- 오류 파일 건너뛰기
- PDF 병합 및 자동 다운로드
- 임시 파일 정리 API

## 빠른 실행 (로컬)
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

브라우저에서 `http://127.0.0.1:8000` 접속

### Supabase 환경변수 설정
인증 기능을 사용하려면 아래 환경변수가 필요합니다.

- `SUPABASE_URL` (예: `https://<project-ref>.supabase.co`)
- `SUPABASE_ANON_KEY`
- `SUPABASE_JWT_AUDIENCE` (기본: `authenticated`)
- `APP_ALLOWED_ORIGINS` (예: `http://127.0.0.1:8000,http://localhost:8000`)
- `ADMIN_EMAILS` (콤마 구분, 예: `admin@admin,owner@example.com`)
- `TOSS_CLIENT_KEY` (Toss 결제위젯 클라이언트 키)
- `TOSS_SECRET_KEY` (Toss 시크릿 키, 서버 승인 API 전용)

로컬에서는 `.env.example`를 참고해 `.env`를 생성한 뒤 실행하세요.

### Toss 결제 키 발급 위치
- [Toss Payments 개발자센터](https://developers.tosspayments.com/) 로그인
- **개발자센터 > API 키** 메뉴에서 상점(MID)을 선택
- 결제위젯용 `Client Key`, `Secret Key`를 복사해 환경변수에 설정
- 테스트는 `test_ck_...`, `test_sk_...` 키를 사용하고, 운영 전환 시 `live_...` 키로 교체

## Docker 실행
```bash
docker compose up --build
```

## Render 배포 (권장)
이 프로젝트는 LibreOffice/ImageMagick 같은 시스템 바이너리에 의존하므로 Vercel Serverless에 적합하지 않습니다.

1. GitHub 저장소를 Render에 연결
2. **New +** → **Web Service**
3. 저장소 선택 후 `render.yaml` 사용(자동 인식)
4. Render Environment에서 반드시 설정: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `APP_ALLOWED_ORIGINS`  
   - 둘 중 하나라도 비어 있으면 메인 화면 우측 상단에 **인증 설정 오류**가 표시됩니다.  
   - `APP_ALLOWED_ORIGINS`에는 배포 URL을 포함하세요 (예: `https://<서비스>.onrender.com`). 필요하면 로컬과 콤마로 병기합니다.
5. 배포 완료 후 `https://<서비스주소>/healthz` 확인
6. 서비스 URL 접속 후 웹 UI 사용

참고:
- Render는 `PORT` 환경변수를 자동 주입하며, Docker CMD에서 이를 사용하도록 설정되어 있습니다.
- 임시 파일은 컨테이너 파일시스템에 저장되므로 재배포/재시작 시 초기화됩니다.

## API
- `POST /api/upload` 파일 업로드 + 변환 시작
- `GET /api/progress/{job_id}` 폴링 진행 조회
- `GET /api/progress-stream/{job_id}` SSE 진행 조회
- `POST /api/skip/{job_id}/{file_id}` 오류 파일 건너뛰기
- `POST /api/merge` PDF 병합
- `GET /api/download/{merge_id}` 병합 파일 다운로드
- `DELETE /api/cleanup/{job_id}` 임시 파일 삭제

## 참고
- 변환 엔진(soffice, magick, wkhtmltopdf, pandoc)이 없으면 일부 형식은 fallback PDF(텍스트 안내)로 생성됩니다.
- 서버 저장소는 `app/storage`이며, 프로덕션에서는 주기적 TTL 정리 작업을 추가하는 것을 권장합니다.
- 상태 확인 엔드포인트: `GET /healthz`
