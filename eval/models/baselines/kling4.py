"""PhyCoVE adapter for the official Kling 4.0 base_video edit endpoint."""
from pathlib import Path
from urllib.parse import quote

from kling4_client import Kling4Client
from .base import BaselineModel, BaselineResult


class Kling4Baseline(BaselineModel):
    name = 'kling4_0_video'

    def __init__(self, source_url_template='https://hf-mirror.com/datasets/ccmoony/PhyCoVE/resolve/main/{source_video}', **kwargs):
        self.client = Kling4Client(**kwargs)
        self.source_url_template = source_url_template
        super().__init__(**self.client.config, source_url_template=source_url_template)

    def setup(self):
        self.client.setup()

    def teardown(self):
        self.client.close()

    def edit_video(self, source_video: Path, prompt: str, output_path: Path, *, edit_info):
        # Only source path and selected prompt are used. No GT or trajectories are sent.
        source_url = self.source_url_template.format(source_video=quote(edit_info['source_video'], safe='/'))
        result = self.client.edit_video(source_video, source_url, prompt, output_path)
        return BaselineResult(output_video=output_path, elapsed_sec=result['elapsed_sec'], extra={
            key: result.get(key) for key in ('task_id', 'external_id', 'output_sha256',
                                            'output_metadata', 'reused_existing')})
