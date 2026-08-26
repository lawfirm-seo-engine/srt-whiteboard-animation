# 법무법인 선린 Whiteboard Video Builder

기존 `srt-whiteboard-animation`의 손그림 스트림 렌더러는 그대로 유지하고, 반복 제작을 위한 프로젝트 생성 레이어를 추가합니다.

## 1. 프로젝트 만들기

```bash
python scripts/sunrin_build_project.py \
  --template stock-reading-room \
  --title "주식리딩방 사기" \
  --duration 30 \
  --aspect 16:9 \
  --project stock-reading-room-01
```

생성 결과:

```text
projects/stock-reading-room-01/
├── project.json
├── script.srt
├── image-prompts.txt
├── scenes/
└── renders/
```

`project.json`은 장면 순서, 각 장면 시간, 내레이션, 이미지 경로, annotation 경로와 이미지 생성 프롬프트를 관리합니다.

## 2. 장면 그림 만들기

`image-prompts.txt`의 장면별 프롬프트로 각각 독립적인 선화 이미지를 만듭니다. 그림 안에는 문자를 넣지 않습니다. 우측 상단은 선린 로고 안전 영역으로 비워 둡니다.

장면 그림은 다음처럼 저장합니다.

```text
scenes/scene-01.png
scenes/scene-02.png
...
```

## 3. annotation 작성

원본 프로젝트의 `assets/preview.html`을 사용해 각 장면의 의미 단위 영역을 지정합니다. 이미지와 annotation은 반드시 같은 번호를 사용합니다.

```text
scene-01.png
scene-01.annotation.json
```

`sequence`는 실제 이야기 순서와 일치시킵니다. 펜이 먼저 그려야 할 배경/인물/행동/결과 순으로 나누는 것을 권장합니다.

## 4. 원본 손그림 렌더러 사용

환경 준비:

```bash
python scripts/prepare_env.py --check
python scripts/prepare_env.py
```

각 장면 렌더링:

```bash
<ENV_PY> scripts/render_stream_whiteboard.py \
  projects/stock-reading-room-01/scenes/scene-01.png \
  projects/stock-reading-room-01/scenes/scene-01.annotation.json \
  projects/stock-reading-room-01/renders/scene-01.mp4 \
  assets/drawing-hand.png \
  --ink-path grid --color-fill contour-wipe
```

이 단계는 정적인 슬라이드 전환이 아니라 원본 엔진의 실제 스트림 방식으로 펜 끝을 따라 선을 그립니다.

## 5. 최종 합치기

```bash
<ENV_PY> scripts/merge_scenes.py \
  --inputs projects/stock-reading-room-01/renders/scene-01.mp4 projects/stock-reading-room-01/renders/scene-02.mp4 \
  --output projects/stock-reading-room-01/final.mp4
```

## 브랜드 기본값

`sunrin/brand.json`에서 종이 배경, 강조색, 로고, 손 이미지, 마지막 CTA를 관리합니다. 로고 파일은 `assets/sunrin-logo.png`에 두면 됩니다.

## 새 상황 추가

`sunrin/templates/`에 JSON 템플릿을 하나 추가하면 됩니다. 각 장면은 `role`, `weight`, `narration`, `visual`만 정의하면 프로젝트 생성기가 전체 30초 안에서 시간을 자동 배분합니다.

향후 관리자 UI에서는 이 템플릿을 선택하고 주제/길이/화면비를 입력하는 방식으로 연결할 수 있습니다.
