"""Download public model weights only; no user document is read or transmitted."""
import argparse
import os

from .config import MODELS, configure_environment


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--endpoint', default='https://huggingface.co')
    args = parser.parse_args()
    configure_environment()
    os.environ.pop('HF_HUB_OFFLINE', None)
    os.environ.pop('TRANSFORMERS_OFFLINE', None)
    os.environ['HF_ENDPOINT'] = args.endpoint
    from huggingface_hub import snapshot_download
    for name, folder in [('mfd-1.5', 'mfd-1.5-onnx'), ('mfr-1.5', 'mfr-1.5-onnx')]:
        print('准备模型：', name, flush=True)
        snapshot_download('breezedeus/pix2text-' + name, local_dir=MODELS / 'pix2text' / '1.1' / folder,
                          allow_patterns=['*.onnx', '*.json', '*.txt', '*.yaml'], max_workers=2,
                          endpoint=args.endpoint)
    from .ocr import get_engine, write_manifest
    print('验证本地识别组件……', flush=True)
    get_engine(allow_download=True)
    print('模型就绪：', write_manifest(), flush=True)


if __name__ == '__main__':
    main()
