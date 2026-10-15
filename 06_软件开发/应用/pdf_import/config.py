import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
DEV_DIR = APP_DIR.parent
DATA = Path(os.environ.get('MATH2_PDF_HOME', DEV_DIR / 'PDF导入试用' / '用户数据')).resolve()
CACHE = Path(os.environ.get('MATH2_PDF_CACHE', DEV_DIR / '开发依赖' / 'pdf-import-cache')).resolve()
MODELS = CACHE / 'models'
MANIFEST = CACHE / 'models.json'


def configure_environment():
    for path in (DATA, CACHE / 'tmp', MODELS):
        path.mkdir(parents=True, exist_ok=True)
    values = {
        'HF_HOME': str(MODELS / 'huggingface'),
        'XDG_CACHE_HOME': str(MODELS / 'xdg'),
        'YOLO_CONFIG_DIR': str(MODELS / 'ultralytics'),
        'TORCH_HOME': str(MODELS / 'torch'),
        'PIX2TEXT_HOME': str(MODELS / 'pix2text'),
        'CNOCR_HOME': str(MODELS / 'cnocr'),
        'CNSTD_HOME': str(MODELS / 'cnstd'),
        'MPLCONFIGDIR': str(MODELS / 'matplotlib'),
        'HF_HUB_DISABLE_TELEMETRY': '1',
        'DO_NOT_TRACK': '1',
        'WANDB_MODE': 'disabled',
        'WANDB_DISABLED': 'true',
        'YOLO_AUTOINSTALL': 'false',
        'YOLO_OFFLINE': 'true',
        'TOKENIZERS_PARALLELISM': 'false',
        'TEMP': str(CACHE / 'tmp'),
        'TMP': str(CACHE / 'tmp'),
    }
    for key in ('HF_HOME', 'XDG_CACHE_HOME', 'YOLO_CONFIG_DIR', 'TORCH_HOME', 'PIX2TEXT_HOME', 'CNOCR_HOME', 'CNSTD_HOME', 'MPLCONFIGDIR'):
        Path(values[key]).mkdir(parents=True, exist_ok=True)
    os.environ.update(values)


CHAPTERS = {
    '高等数学': ['函数、极限与连续', '一元函数微分学', '一元函数积分学', '定积分应用', '多元函数微分学', '二重积分', '常微分方程'],
    '线性代数': ['行列式', '矩阵', '向量与矩阵秩', '线性方程组', '特征值与相似', '二次型'],
}


def subject_for(chapter):
    return next((subject for subject, chapters in CHAPTERS.items() if chapter in chapters), '')
