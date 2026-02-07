# CPU/RAM Simulator

Aplicacao web que simula carga de **CPU** e **memoria** dentro de um Pod Kubernetes/OpenShift. Util para testar limites de recursos, autoscaling (HPA/VPA), comportamento de OOMKill e observabilidade.

## Como funciona

A aplicacao e uma API FastAPI que, ao receber um comando **Start**, dispara:

- **N processos** (`cpu_workers`) que executam um loop infinito de operacoes matematicas para saturar nucleos de CPU.
- **Alocacao de memoria** em blocos de 1 MiB ate atingir o valor alvo (`mem_mib`), mantendo as referencias em memoria para evitar garbage collection.
- Um **timer** que encerra automaticamente o job apos o tempo configurado (`seconds`).

A interface web se conecta via **WebSocket** e exibe em tempo real: estado (running/stopped), tempo restante, memoria alocada, quantidade de workers e ticks.

## Estrutura do projeto

```
cpu-mem-simulator/
├── app/
│   ├── main.py                  # Aplicacao FastAPI (API + WebSocket)
│   ├── requirements.txt         # Dependencias Python (FastAPI, Uvicorn)
│   ├── Containerfile            # Build da imagem (UBI9 Python 3.11)
│   ├── templates/
│   │   └── index.html           # Interface web (HTML + JS)
│   └── tekton/
│       ├── tasks.yaml           # Tekton Tasks (show-context, update-gitops-tag)
│       ├── pipeline.yaml        # Pipeline: clone -> show -> build-and-push
│       ├── pipelinerun.yaml     # PipelineRun de exemplo
│       ├── pvc-workspace.yaml   # PVC para workspace compartilhado
│       └── serviceaccount.yaml  # ServiceAccount para o pipeline
├── gitops/
│   ├── base/
│   │   ├── deployment.yaml      # Deployment com requests/limits (1200m CPU, 2Gi RAM)
│   │   ├── service.yaml         # Service (porta 80 -> 8080)
│   │   ├── route.yaml           # Route OpenShift (TLS edge)
│   │   └── kustomization.yaml
│   └── overlays/
│       └── dev/
│           ├── namespace.yaml   # Namespace: cpu-mem-sim
│           └── kustomization.yaml  # Overlay com image tag
└── README.md
```

## Executando localmente

```bash
cd app
pip install -r requirements.txt
python main.py
```

A aplicacao sobe em `http://localhost:8080`.

## Executando com container

```bash
# Build
podman build -f app/Containerfile -t cpu-mem-sim:latest .

# Run
podman run --rm -p 8080:8080 cpu-mem-sim:latest
```

## API

| Metodo | Endpoint      | Descricao                              |
|--------|---------------|----------------------------------------|
| GET    | `/`           | Interface web                          |
| POST   | `/api/start`  | Inicia o job de stress                 |
| POST   | `/api/stop`   | Para o job                             |
| GET    | `/api/status` | Retorna o estado atual (JSON)          |
| WS     | `/ws`         | WebSocket com status atualizado a cada 1s |

### POST `/api/start`

```json
{
  "mem_mib": 1900,
  "cpu_workers": 2,
  "seconds": 120
}
```

| Parametro     | Min  | Max   | Default | Descricao                        |
|---------------|------|-------|---------|----------------------------------|
| `mem_mib`     | 64   | 3000  | 1900    | Memoria alvo em MiB              |
| `cpu_workers` | 1    | 32    | 2       | Numero de processos de CPU burn  |
| `seconds`     | 5    | 3600  | 120     | Duracao do job em segundos       |

## Deploy no OpenShift

Os manifests estao organizados com **Kustomize**:

```bash
# Deploy no namespace cpu-mem-sim (overlay dev)
oc apply -k gitops/overlays/dev
```

O Deployment esta configurado com:
- **Requests/Limits**: 1200m CPU, 2Gi RAM
- **Probes**: readiness em `/` e liveness em `/api/status`
- **Route**: TLS edge termination

## CI/CD com Tekton

O pipeline Tekton realiza:

1. **git-clone** - Clona o repositorio
2. **show-context** - Lista o conteudo do workspace (debug)
3. **buildah** - Builda a imagem com o `Containerfile` e faz push para o registry

Existe tambem a task `update-gitops-tag` que atualiza a tag da imagem no `kustomization.yaml` do overlay e faz push, permitindo um fluxo GitOps completo.

```bash
# Criar recursos do pipeline
oc apply -f app/tekton/tasks.yaml
oc apply -f app/tekton/pipeline.yaml
oc apply -f app/tekton/serviceaccount.yaml

# Executar o pipeline (ajuste GIT_URL e IMAGE)
oc create -f app/tekton/pipelinerun.yaml
```

## Casos de uso

- **Testar limites de recursos**: Configurar `mem_mib` acima do limit do Pod para observar OOMKill.
- **Validar HPA**: Gerar carga de CPU para disparar autoscaling horizontal.
- **Observabilidade**: Validar dashboards, alertas e metricas de consumo de recursos.
- **Chaos Engineering**: Simular cenarios de alta utilizacao de recursos em ambientes controlados.

## Tecnologias

- **Python 3.11** + **FastAPI** + **Uvicorn**
- **Containerfile** baseado em **UBI9** (Red Hat Universal Base Image)
- **Kustomize** para gerenciamento de manifests Kubernetes
- **Tekton Pipelines** para CI/CD
- **OpenShift** Routes para exposicao do servico
