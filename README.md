# ComfyUI RunPod Template

A streamlined and feature-rich RunPod template for ComfyUI with an enhanced user interface, model management, and custom nodes.


## 🌟 Features

- **Modern, Clean UI** - Intuitive interface with tabbed sections and responsive design
- **Real-time Log Viewer** - Docker-style formatted logs with auto-scroll functionality
- **Model Management** - Download models from Civitai, Hugging Face, and Google Drive
- **Pre-installed Custom Nodes** - Extensive collection of the most popular custom nodes
- **One-click Access** - Direct links to ComfyUI and JupyterLab interfaces
- **Output Download** - Quickly download all your generated images in one click

## 🚀 Getting Started

### Starting Your Pod

1. Select this template from the RunPod template library
2. Choose your desired GPU type (recommended at least 24GB VRAM for optimal performance)
3. Start your pod
4. Access the Dashboard at port 8189 from your pod's Connect tab

### Interface Overview

The interface consists of several key sections:

- **Top Controls** - Access links to ComfyUI, JupyterLab, and output downloads
- **Pre-installed Section** - View all custom nodes and models included in the template
- **Logs Section** - Monitor the ComfyUI logs in real-time with auto-scroll
- **Model Downloaders** - Download additional models from popular repositories

## 💾 Model Management

### Available Model Categories

- Checkpoints
- VAE
- LoRA
- UNet
- Diffusion Models
- Text Encoders
- Upscale Models
- CLIP
- ControlNet
- CLIP Vision
- IPAdapter
- Style Models

### Downloading Models

#### From Civitai

1. Navigate to the Civitai downloader tab
2. Enter the model URL from Civitai
3. Add your Civitai API key (optional)
4. Select the appropriate model type
5. Click "Download Model"

#### From Hugging Face

1. Navigate to the Hugging Face downloader tab
2. Enter the direct file URL from Hugging Face
3. Add an access token (optional - only needed for gated or private repos)
4. Select the appropriate model type
5. Click "Download Model"

##### Gated and private repos

Set the `HF_TOKEN` environment variable on your pod to download gated or
private models. It is picked up by both the boot-time downloads driven by
`models_config.json` and the Hugging Face downloader tab, so you only need to
set it once. A token pasted into the downloader tab takes priority over the
environment variable for that one download.

Create a token at https://huggingface.co/settings/tokens with `read` access,
and accept the model's license on its Hugging Face page first - a token alone
does not grant access to a gated repo you have not been approved for.

The token is only ever sent to `huggingface.co` URLs, never to Civitai, Google
Drive, or any other host in your config, and it is stripped out of logs and the
dashboard's error messages.

Note that a token controls *access*, not bandwidth - it will not make public
models download any faster.

#### From Google Drive

1. Navigate to the Google Drive downloader tab
2. Enter the Google Drive URL or file ID
3. Select the appropriate model type
4. Optionally specify a custom filename
5. Click "Download Model"

## 🌐 Running Outside RunPod

On RunPod the dashboard builds its **Open ComfyUI** and **Open JupyterLab**
links from `RUNPOD_POD_ID`, and nothing needs configuring.

Elsewhere it falls back to the hostname you reached the dashboard on plus the
container ports, `8188` and `8888`. That is correct for local Docker and for an
SSH tunnel, but wrong on hosts that publish containers on randomly assigned
ports, such as Vast.ai - the dashboard has no way to learn which external port
maps to `8188`.

Set these when that is the case:

| Variable | Example |
| --- | --- |
| `COMFYUI_PUBLIC_URL` | `http://63.12.4.9:40001` |
| `JUPYTER_PUBLIC_URL` | `http://63.12.4.9:40002` |

Either one may be set on its own; whichever is left unset keeps the default
behaviour. A bare `host:port` is accepted and assumed to be `http://`.

## 🧩 Custom Nodes

This template comes with the following custom nodes pre-installed:

- ComfyUI-Manager
- ComfyUI-Impact-Pack
- ComfyUI_essentials
- ComfyUI-Inspire-Pack
- comfyui_controlnet_aux
- DZ-FaceDetailer
- ComfyUI_IPAdapter_plus
- ComfyUI_UltimateSDUpscale
- ComfyUI-VideoHelperSuite
- comfyui-inpaint-nodes
- ComfyUI-KJNodes
- ComfyUI-GGUF
- rgthree-comfy
- ComfyUI_Custom_Nodes_AlekPet
- ComfyUI-Gemini-API
- ComfyUI-RED-UNO
- Bjornulf_custom_nodes
- ComfyUI-Custom-Scripts


### Backing Up Your Work

To back up your work:
1. Use the "Download Outputs" button to get generated images
2. For workflows, save them through the ComfyUI interface


## 🙏 Acknowledgements

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) by comfyanonymous
- All custom node developers for their valuable contributions
- RunPod.io for the GPU cloud infrastructure

For more information, visit [PromptAlchemist on Facebook](https://www.facebook.com/PromptAlchemist). 