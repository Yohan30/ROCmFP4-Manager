"""Wrapper simple pour l'API HuggingFace Hub."""

from huggingface_hub import HfApi, list_repo_files
from typing import List, Dict, Optional
import re


class HuggingFaceAPI:
    """Recherche et informations sur les modèles GGUF ROCmFP4."""

    ROCMFP4_PATTERN = re.compile(r"ROCmFP4|rocmfp4|ROCmFPX|rocmfpx")

    def __init__(self):
        self._api = HfApi()

    def search_models(self, query: str = "", limit: Optional[int] = None) -> List[Dict]:
        """Cherche des modèles GGUF potentiellement ROCmFP4.

        Par défaut (limit=None), renvoie TOUS les modèles correspondant à la
        recherche, sans plafond. Un limit explicite peut être passé pour
        restreindre le nombre de résultats.
        """
        results = []

        try:
            # filter="gguf" : ne renvoyer que les modèles GGUF (côté serveur),
            # ce qui rend la liste pertinente et limite fortement le volume
            # pour les requêtes génériques.
            models = self._api.list_models(
                search=query,
                filter="gguf",
                sort="downloads",
                limit=limit,  # None = tous les résultats (pagination complète)
            )
        except Exception as e:
            return []

        import requests
        import concurrent.futures

        def fetch_total_size(repo_id: str) -> int:
            """Récupère la taille totale des GGUF d'un repo via HEAD."""
            try:
                files = list_repo_files(repo_id)
                ggufs = [f for f in files if f.endswith(".gguf")]
                total = 0
                for f in ggufs[:3]:  # Max 3 HEAD requests (suffisant car peu de fichiers GGUF par repo)
                    url = f"https://huggingface.co/{repo_id}/resolve/main/{f}"
                    resp = requests.head(url, allow_redirects=True, timeout=5)
                    if resp.status_code == 200:
                        total += int(resp.headers.get("Content-Length", 0))
                return total
            except Exception:
                return 0

        for model in models:
            model_id = model.modelId
            description = (getattr(model, 'description', '') or '').lower()
            tags = [t.lower() for t in getattr(model, 'tags', [])]
            pipeline = (getattr(model, 'pipeline_tag', '') or '').lower()

            # Ne garder que les modèles GGUF (text-generation)
            is_gguf = 'gguf' in model_id.lower() or 'gguf' in description or 'gguf' in tags
            is_text = pipeline in ('text-generation', '')

            if not is_gguf and not is_text:
                continue

            is_rocmfp4 = bool(self.ROCMFP4_PATTERN.search(model_id))

            # Taille totale: calculée plus bas pour les 10 premiers uniquement
            # (trop lent pour tous les résultats)
            total_size = 0

            results.append({
                "id": model_id,
                "name": model_id.split("/")[-1],
                "author": model_id.split("/")[0],
                "downloads": getattr(model, "downloads", 0),
                "is_rocmfp4": is_rocmfp4,
                "total_size": total_size,
                "pipeline_tag": pipeline,
            })

        # Trier: ROCmFP4 en premier, puis par téléchargements
        results.sort(key=lambda r: (not r["is_rocmfp4"], -r["downloads"]))

        # Fetch sizes for top results only (max 10)
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_idx = {}
            for i, r in enumerate(results):
                if i < 10:  # Only first 10
                    future = executor.submit(fetch_total_size, r["id"])
                    future_to_idx[future] = i
            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx]["total_size"] = future.result()
                except Exception:
                    pass

        return results

    def list_gguf_files(self, repo_id: str) -> List[Dict]:
        """Liste les fichiers GGUF d'un dépôt avec leurs tailles."""
        try:
            files = list_repo_files(repo_id)
            gguf_files = [f for f in files if f.endswith(".gguf")]
        except Exception:
            return []

        import requests
        results = []
        for f in gguf_files:
            size = 0
            try:
                url = f"https://huggingface.co/{repo_id}/resolve/main/{f}"
                resp = requests.head(url, allow_redirects=True, timeout=10)
                if resp.status_code == 200:
                    size = int(resp.headers.get("Content-Length", 0))
            except Exception:
                pass
            results.append({"filename": f, "size": size})

        return results

    def get_model_info(self, repo_id: str) -> Dict:
        """Récupère les infos d'un modèle."""
        try:
            info = self._api.model_info(repo_id)
            card_data = getattr(info, "card_data", None) or {}
            return {
                "id": info.modelId,
                "description": getattr(info, "description", ""),
                "downloads": getattr(info, "downloads", 0),
                "likes": getattr(info, "likes", 0),
                "tags": list(getattr(info, "tags", [])),
                "gguf_files": self.list_gguf_files(repo_id),
                "config": {
                    "arch": getattr(card_data, "architectures", [None])[0],
                    "license": getattr(card_data, "license", ""),
                    "parameters": getattr(card_data, "parameters", ""),
                }
            }
        except Exception as e:
            return {"id": repo_id, "error": str(e)}
