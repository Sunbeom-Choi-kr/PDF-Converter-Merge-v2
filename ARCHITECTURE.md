# PDF Converter & Merger 아키텍처 정의서

## 1) 문서 목적
- 이 문서는 `pdf` 프로젝트의 구조와 동작 방식을 빠르게 설명하기 위한 아키텍처 정의서입니다.
- 대상 독자는 운영자, 협업 개발자, 인수인계 대상자입니다.

## 2) 시스템 개요
- 본 서비스는 여러 형식의 파일을 PDF로 변환한 뒤 순서대로 병합하여 단일 PDF를 내려주는 웹 애플리케이션입니다.
- 서버는 `FastAPI` 단일 프로세스로 동작하며, 프런트엔드는 정적 파일(`HTML/CSS/JS`)로 제공됩니다.
- 변환은 파일 확장자별로 외부 바이너리(LibreOffice, ImageMagick, wkhtmltopdf, pandoc) 또는 파이썬 fallback 로직을 사용합니다.

## 3) 상위 아키텍처
- **Frontend (정적 웹 UI)**: 파일 선택, 순서 조정, 업로드, 진행률 표시, 병합 요청, 다운로드
- **API Layer (FastAPI)**: 업로드/진행률/SSE/병합/다운로드/정리 엔드포인트 제공
- **Job Orchestrator (`JobStore`)**: 작업 생성, 파일별 상태 관리, 변환 실행, 병합 수행, 정리
- **Converter Service**: 확장자별 변환 전략 수행
- **Storage (로컬 파일시스템)**: 세션 디렉터리 기반 임시 저장 및 결과물 관리

## 4) 주요 구성요소

### 4.1 API 엔트리포인트
- 파일: `app/main.py`
- 역할:
  - `/api/upload`: 업로드 수신 후 작업 생성 및 백그라운드 변환 시작
  - `/api/progress/{job_id}`: 진행률 조회
  - `/api/progress-stream/{job_id}`: SSE 진행률 스트리밍
  - `/api/skip/{job_id}/{file_id}`: 오류 파일 건너뛰기
  - `/api/merge`: 변환 완료 파일 병합
  - `/api/download/{merge_id}`: 병합 PDF 다운로드
  - `/api/cleanup/{job_id}`: 임시 파일 정리
  - `/healthz`: 헬스체크

### 4.2 작업/상태 관리
- 파일: `app/services/jobs.py`
- 핵심 데이터 모델:
  - `Job`: 작업 단위(세션 폴더, 파일 목록, 병합 상태, 결과 파일)
  - `FileTask`: 개별 파일 단위(원본명, 저장 경로, 변환 PDF 경로, 상태, 에러)
- 상태 값:
  - 파일: `waiting` -> `converting` -> `done | error | skipped`
  - 병합: `idle` -> `merging` -> `done | error`
- 제약:
  - 최대 파일 수 20개
  - 단일 파일 최대 50MB
  - 총합 최대 200MB
  - TTL(기본 30분) 기반 정리 메서드 보유

### 4.3 변환 엔진
- 파일: `app/services/converter.py`
- 전략:
  - Office 계열(`.docx/.xlsx/.pptx/.../.hwp/.hwpx`): `soffice --headless --convert-to pdf`
  - 이미지 계열: `magick` 또는 `convert`, 실패 시 `ReportLab/ImageReader` fallback
  - HTML: `wkhtmltopdf`
  - Markdown: `pandoc`
  - Text/JSON: 텍스트 미리보기 fallback PDF 생성
  - PDF: 복사(pass-through)

## 5) 데이터/제어 흐름
1. 사용자가 UI에서 파일 선택 및 순서 결정
2. `/api/upload` 호출로 파일과 출력명 전송
3. 서버가 `Job` 생성, 파일을 `app/storage/{job_id}`에 저장
4. 백그라운드에서 파일별 `convert_to_pdf()` 수행
5. 클라이언트는 SSE(`/api/progress-stream/{job_id}`)로 상태를 실시간 수신
6. 모든 파일 처리 후 `/api/merge` 호출
7. `PdfWriter`로 성공/건너뜀 파일을 순서대로 병합
8. `/api/download/{merge_id}`로 결과 파일 다운로드
9. 필요 시 `/api/cleanup/{job_id}`로 세션 정리

## 6) 저장소 구조
- 루트: `app/storage`
- 작업별 세션 디렉터리:
  - 원본 파일: `app/storage/{job_id}/{index}_{file_id}_{original_name}`
  - 변환 PDF: `app/storage/{job_id}/pdfs/{index}_{file_id}.pdf`
  - 병합 결과: `app/storage/{job_id}/{output_name}.pdf`

## 7) 배포/런타임 아키텍처
- Docker 기반 단일 서비스 배포(`render.yaml`)
- 베이스 이미지: `python:3.11-slim-bullseye`
- 시스템 의존성:
  - `libreoffice`, `libreoffice-writer`, `libreoffice-java-common`, `default-jre`
  - `imagemagick`, `wkhtmltopdf`, `pandoc`, `fonts-noto-cjk`
- 서버 포트는 `PORT` 환경변수 기반으로 `uvicorn` 실행

## 8) 장애/제약 사항
- `.hwp/.hwpx`는 환경별 LibreOffice 필터 지원 여부에 따라 실패 가능
  - 실패 시 에러 메시지에 `stderr/stdout` 또는 필터 미지원 가능성이 노출됨
- ImageMagick 정책(`policy.xml`)으로 PDF 쓰기 차단 시 이미지 변환 실패 가능
  - 현재는 파이썬 fallback으로 우회
- 인메모리 `jobs` 맵 사용으로 인해 프로세스 재시작 시 작업 상태는 유실됨
- 스토리지는 컨테이너 로컬 파일시스템이므로 재배포 시 파일이 초기화됨

## 9) 보안/운영 고려사항
- 현재 CORS는 전체 허용(`*`)이며, 운영 환경에서는 도메인 제한 권장
- 파일 업로드 용량 제한은 애플리케이션 레벨에서 수행
- 악성 파일 검증(백신/콘텐츠 검증)은 현재 미구현
- 장기 운영 시 주기적 정리(`cleanup_expired`) 스케줄링 권장

## 10) 향후 개선 포인트
- 작업 상태 저장소를 외부(예: Redis/DB)로 분리해 재시작 내구성 강화
- 변환 워커 큐 도입으로 동시성/확장성 개선
- `.hwp` 전용 변환 경로(외부 서비스/API) 분리
- 업로드/변환/병합 단계별 상세 메트릭 및 알림 체계 추가

