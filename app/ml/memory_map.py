"""Mapa mental do agente, responsável por memórias aprendidas."""

import os
import pickle
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List


@dataclass
class MemoriaCelula:
    id: int
    padrao: str
    contexto: List[str]
    previsao: str
    acertos: int = 0
    erros: int = 0
    confianca: float = 0.5
    criado_em: datetime = field(default_factory=datetime.now)
    ultimo_uso: datetime = field(default_factory=datetime.now)

    @property
    def precisao(self) -> float:
        total = self.acertos + self.erros
        return (self.acertos / total) if total > 0 else 0.5

    @property
    def peso(self) -> float:
        horas_desde_uso = (datetime.now() - self.ultimo_uso).total_seconds() / 3600
        fator_recencia = max(0.3, 1 - horas_desde_uso / 720)
        return self.precisao * self.confianca * fator_recencia

    def atualizar(self, acertou: bool):
        if acertou:
            self.acertos += 1
            self.confianca = min(0.95, self.confianca * 1.05)
        else:
            self.erros += 1
            self.confianca = max(0.3, self.confianca * 0.95)
        self.ultimo_uso = datetime.now()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "padrao": self.padrao,
            "contexto": self.contexto,
            "previsao": self.previsao,
            "acertos": self.acertos,
            "erros": self.erros,
            "confianca": self.confianca,
            "criado_em": self.criado_em.isoformat(),
            "ultimo_uso": self.ultimo_uso.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            id=data["id"],
            padrao=data["padrao"],
            contexto=data["contexto"],
            previsao=data["previsao"],
            acertos=data.get("acertos", 0),
            erros=data.get("erros", 0),
            confianca=data.get("confianca", 0.5),
            criado_em=datetime.fromisoformat(data["criado_em"])
            if isinstance(data["criado_em"], str)
            else data["criado_em"],
            ultimo_uso=datetime.fromisoformat(data["ultimo_uso"])
            if isinstance(data["ultimo_uso"], str)
            else data["ultimo_uso"],
        )


class MapaMental:
    """Repositório de memórias do agente."""

    def __init__(self, capacidade: int = 1000, arquivo: str = "mapa_mental.pkl"):
        self.celulas: Dict[int, MemoriaCelula] = {}
        self.proximo_id = 0
        self.capacidade = capacidade
        self.arquivo = arquivo
        self.indice_contexto: Dict[str, List[int]] = {}
        self._carregar_auto()
        print(f"🗺️ Mapa Mental inicializado: {len(self.celulas)} memórias")

    def adicionar_memoria(self, padrao: str, contexto: List[str], previsao: str) -> int:
        contexto_hash = self._hash_contexto(contexto)
        if contexto_hash in self.indice_contexto:
            for cell_id in self.indice_contexto[contexto_hash]:
                if self.celulas[cell_id].padrao == padrao:
                    return cell_id

        nova = MemoriaCelula(self.proximo_id, padrao, contexto.copy(), previsao)
        self.celulas[self.proximo_id] = nova
        self.indice_contexto.setdefault(contexto_hash, []).append(self.proximo_id)

        if len(self.celulas) > self.capacidade:
            self._limpar_memorias_fracas()

        self.proximo_id += 1
        if self.proximo_id % 10 == 0:
            self._salvar_auto()
        return self.proximo_id - 1

    def consultar(self, contexto: List[str], limite: int = 5) -> List[MemoriaCelula]:
        if not contexto:
            return []

        contexto_hash = self._hash_contexto(contexto)
        resultados = []

        if contexto_hash in self.indice_contexto:
            for cell_id in self.indice_contexto[contexto_hash]:
                cell = self.celulas[cell_id]
                resultados.append((cell, cell.peso))

        if len(resultados) < limite and len(contexto) > 2:
            for i in range(1, len(contexto)):
                ctx_parcial = contexto[:-i]
                if not ctx_parcial:
                    continue
                hash_parcial = self._hash_contexto(ctx_parcial)
                if hash_parcial in self.indice_contexto:
                    for cell_id in self.indice_contexto[hash_parcial]:
                        cell = self.celulas[cell_id]
                        if not any(r[0].id == cell.id for r in resultados):
                            resultados.append((cell, cell.peso * 0.7))

        resultados.sort(key=lambda item: item[1], reverse=True)
        return [resultado[0] for resultado in resultados[:limite]]

    def atualizar_memoria(self, cell_id: int, acertou: bool):
        if cell_id in self.celulas:
            self.celulas[cell_id].atualizar(acertou)
            self._salvar_auto()

    def _hash_contexto(self, contexto: List[str]) -> str:
        filtrados = [resultado for resultado in contexto if resultado != "TIE"][:5]
        return "_".join(filtrados) if filtrados else "vazio"

    def _limpar_memorias_fracas(self):
        fracas = [(cell_id, cell.peso) for cell_id, cell in self.celulas.items() if cell.peso < 0.25]
        fracas.sort(key=lambda item: item[1])

        remover = len(fracas) // 4
        for i in range(min(remover, len(fracas))):
            self._remover_memoria(fracas[i][0])

        if remover > 0:
            print(f"🧹 Limpeza: removidas {remover} memórias fracas")

    def _remover_memoria(self, cell_id: int):
        if cell_id not in self.celulas:
            return
        cell = self.celulas[cell_id]
        contexto_hash = self._hash_contexto(cell.contexto)
        if contexto_hash in self.indice_contexto:
            self.indice_contexto[contexto_hash] = [i for i in self.indice_contexto[contexto_hash] if i != cell_id]
        del self.celulas[cell_id]

    def _salvar_auto(self):
        try:
            estado = {
                "proximo_id": self.proximo_id,
                "celulas": {str(cell_id): cell.to_dict() for cell_id, cell in self.celulas.items()},
            }
            with open(self.arquivo, "wb") as file_obj:
                pickle.dump(estado, file_obj)
        except Exception as exc:
            print(f"⚠️ Erro ao salvar mapa mental: {exc}")

    def _carregar_auto(self):
        try:
            if not os.path.exists(self.arquivo):
                return
            with open(self.arquivo, "rb") as file_obj:
                estado = pickle.load(file_obj)

            self.proximo_id = estado.get("proximo_id", 0)
            for data in estado.get("celulas", {}).values():
                cell = MemoriaCelula.from_dict(data)
                self.celulas[cell.id] = cell

            self.indice_contexto = {}
            for cell in self.celulas.values():
                ctx_hash = self._hash_contexto(cell.contexto)
                self.indice_contexto.setdefault(ctx_hash, []).append(cell.id)

            print(f"🗺️ Mapa Mental carregado: {len(self.celulas)} memórias")
        except Exception as exc:
            print(f"⚠️ Erro ao carregar mapa mental: {exc}")

    def get_stats(self) -> dict:
        if not self.celulas:
            return {"total": 0, "precisao_media": 0, "padroes": {}}

        precisao_media = sum(c.precisao for c in self.celulas.values()) / len(self.celulas)
        padroes: Dict[str, int] = {}
        for cell in self.celulas.values():
            padroes[cell.padrao] = padroes.get(cell.padrao, 0) + 1

        return {
            "total": len(self.celulas),
            "capacidade": self.capacidade,
            "precisao_media": round(precisao_media * 100, 1),
            "padroes": padroes,
        }
