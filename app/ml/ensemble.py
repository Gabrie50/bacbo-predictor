"""Sistema ensemble com especialistas e mapa mental."""

import os
import pickle
import random
from collections import deque
from datetime import datetime
from typing import Dict, List, Optional

from app.ml.indicators import BacBoIndicators
from app.ml.memory_map import MapaMental


class AgenteEspecialista:
    """Especialista em um padrão específico."""

    def __init__(self, nome: str, padrao_nome: str, peso_inicial: float = 0.5):
        self.nome = nome
        self.padrao_nome = padrao_nome
        self.peso_aprendido = peso_inicial
        self.acertos = 0
        self.erros = 0
        self.total_usos = 0
        self.ultimo_uso = datetime.now()
        self.historico_precisao = deque(maxlen=50)

    @property
    def precisao(self) -> float:
        total = self.acertos + self.erros
        return (self.acertos / total) if total > 0 else 0.5

    @property
    def peso_efetivo(self) -> float:
        return self.peso_aprendido * (0.5 + self.precisao * 0.5)

    def registrar_resultado(self, acertou: bool):
        if acertou:
            self.acertos += 1
            self.peso_aprendido = min(2.0, self.peso_aprendido * 1.03)
        else:
            self.erros += 1
            self.peso_aprendido = max(0.3, self.peso_aprendido * 0.97)
        self.total_usos += 1
        self.historico_precisao.append(self.precisao)
        self.ultimo_uso = datetime.now()

    def get_stats(self) -> dict:
        return {
            "nome": self.nome,
            "padrao": self.padrao_nome,
            "peso": round(self.peso_efetivo, 3),
            "acertos": self.acertos,
            "erros": self.erros,
            "total_usos": self.total_usos,
            "precisao": round(self.precisao * 100, 1),
        }


class EnsembleAgentes:
    """Conjunto de agentes especialistas trabalhando em votação ponderada."""

    def __init__(
        self,
        arquivo_estado: str = "ensemble_estado.pkl",
        indicadores: Optional[BacBoIndicators] = None,
        mapa_mental: Optional[MapaMental] = None,
    ):
        self.agentes: Dict[str, AgenteEspecialista] = {}
        self.indicadores = indicadores or BacBoIndicators()
        self.mapa_mental = mapa_mental or MapaMental()
        self.arquivo_estado = arquivo_estado
        self.total_previsoes = 0
        self.acertos = 0
        self.erros = 0
        self.historico_votacoes = deque(maxlen=200)
        self._criar_especialistas()
        self._carregar_auto()

        print("\n🎯 ENSEMBLE DE AGENTES INICIALIZADO!")
        print(f"   📊 {len(self.agentes)} especialistas ativos")
        print(f"   🗺️ Mapa mental: {self.mapa_mental.get_stats()['total']} memórias")
        percentual = (self.acertos / self.total_previsoes * 100) if self.total_previsoes > 0 else 0
        print(f"   📈 Precisão atual: {percentual:.1f}%")

    def _criar_especialistas(self):
        especialistas = [
            ("streak_3_reversao", 0.80, "Reversão após 3+ streaks"),
            ("delta_correcao", 0.85, "Correção de delta"),
            ("tie_6_player", 0.95, "TIE 6 → PLAYER"),
            ("duplo_tie_72", 0.77, "Duplo TIE → BANKER"),
            ("vibracao_tie", 0.55, "Vibração para TIE"),
            ("alternancia", 0.60, "Alternância"),
            ("repeticao", 0.40, "Repetição"),
        ]

        for padrao, peso, descricao in especialistas:
            nome = f"Esp_{padrao[:12]}"
            self.agentes[padrao] = AgenteEspecialista(nome, padrao, peso)
            print(f"   ✅ {descricao}: peso inicial {peso}")

    def prever(self, historico: List[dict]) -> dict:
        if len(historico) < 30:
            return {
                "previsao": "AGUARDANDO",
                "confianca": 0,
                "modo": "INICIALIZACAO",
                "estrategias": [],
            }

        padroes_detectados = self.indicadores.detectar_padroes(historico)
        votos = {"BANKER": 0.0, "PLAYER": 0.0, "TIE": 0.0}
        votos_detalhados = []

        for padrao_info in padroes_detectados:
            padrao_nome = padrao_info["nome"]
            if padrao_nome not in self.agentes:
                continue
            especialista = self.agentes[padrao_nome]
            peso_voto = especialista.peso_efetivo * (padrao_info["confianca"] / 100)
            votos[padrao_info["previsao"]] += peso_voto
            votos_detalhados.append(
                {
                    "agente": especialista.nome,
                    "padrao": padrao_nome,
                    "previsao": padrao_info["previsao"],
                    "confianca": padrao_info["confianca"],
                    "peso": round(especialista.peso_efetivo, 3),
                    "detalhes": padrao_info.get("detalhes", ""),
                }
            )

        contexto = [r.get("resultado") for r in historico[:10] if r.get("resultado") != "TIE"][:5]
        memorias = self.mapa_mental.consultar(contexto, limite=5)
        for memoria in memorias:
            votos[memoria.previsao] += memoria.peso * 0.7
            votos_detalhados.append(
                {
                    "agente": "MEMORIA",
                    "padrao": memoria.padrao,
                    "previsao": memoria.previsao,
                    "confianca": round(memoria.precisao * 100, 1),
                    "peso": round(memoria.peso, 3),
                    "detalhes": "Memória aprendida",
                }
            )

        total_votos = sum(votos.values())
        if total_votos > 0:
            previsao_final = max(votos, key=votos.get)
            confianca = (votos[previsao_final] / total_votos) * 100
        else:
            ultimos = [r.get("resultado") for r in historico[:20] if r.get("resultado") != "TIE"]
            if ultimos:
                banker = ultimos.count("BANKER")
                player = ultimos.count("PLAYER")
                previsao_final = "BANKER" if banker > player else "PLAYER"
                confianca = 55
            else:
                previsao_final = random.choice(["BANKER", "PLAYER"])
                confianca = 50
            votos_detalhados.append(
                {
                    "agente": "FALLBACK",
                    "padrao": "tendencia",
                    "previsao": previsao_final,
                    "confianca": confianca,
                    "peso": 0.5,
                }
            )

        self._ultimo_contexto = contexto
        self._ultimos_padroes = padroes_detectados
        self._ultimas_memorias = memorias
        self._ultima_previsao = previsao_final
        self._ultimos_votos = votos_detalhados

        estrategias = [f"{v['padrao']}({v['confianca']:.0f}%)" for v in votos_detalhados[:8] if v["agente"] != "FALLBACK"]
        simbolo = "🟡" if previsao_final == "TIE" else ("🔴" if previsao_final == "BANKER" else "🔵")

        return {
            "previsao": previsao_final,
            "simbolo": simbolo,
            "confianca": round(confianca),
            "modo": "ENSEMBLE",
            "estrategias": estrategias[:5],
            "especialistas_ativos": len(padroes_detectados),
            "memorias_ativas": len(memorias),
            "total_votos": len(votos_detalhados),
        }

    def aprender(self, resultado_real: str):
        if not hasattr(self, "_ultima_previsao"):
            return False

        acertou = self._ultima_previsao == resultado_real
        self.total_previsoes += 1
        if acertou:
            self.acertos += 1
        else:
            self.erros += 1

        for padrao_info in getattr(self, "_ultimos_padroes", []):
            padrao_nome = padrao_info["nome"]
            if padrao_nome in self.agentes:
                self.agentes[padrao_nome].registrar_resultado(padrao_info["previsao"] == resultado_real)

        for memoria in getattr(self, "_ultimas_memorias", []):
            self.mapa_mental.atualizar_memoria(memoria.id, memoria.previsao == resultado_real)

        if not acertou and getattr(self, "_ultimo_contexto", None):
            novo_padrao = f"aprendido_{'_'.join(self._ultimo_contexto)}"
            self.mapa_mental.adicionar_memoria(novo_padrao, self._ultimo_contexto, self._ultima_previsao)

        if self.total_previsoes % 50 == 0:
            self._salvar_auto()
        return acertou

    def get_stats(self) -> dict:
        precisao = (self.acertos / self.total_previsoes * 100) if self.total_previsoes > 0 else 0
        especialistas_stats = [agente.get_stats() for agente in self.agentes.values()]
        return {
            "total_previsoes": self.total_previsoes,
            "acertos": self.acertos,
            "erros": self.erros,
            "precisao": round(precisao, 1),
            "especialistas": sorted(especialistas_stats, key=lambda item: item["precisao"], reverse=True),
            "mapa_mental": self.mapa_mental.get_stats(),
        }

    def _salvar_auto(self):
        try:
            estado = {
                "agentes": {
                    nome: {
                        "peso_aprendido": agente.peso_aprendido,
                        "acertos": agente.acertos,
                        "erros": agente.erros,
                        "total_usos": agente.total_usos,
                    }
                    for nome, agente in self.agentes.items()
                },
                "total_previsoes": self.total_previsoes,
                "acertos": self.acertos,
                "erros": self.erros,
            }
            with open(self.arquivo_estado, "wb") as file_obj:
                pickle.dump(estado, file_obj)
        except Exception as exc:
            print(f"⚠️ Erro ao salvar ensemble: {exc}")

    def _carregar_auto(self):
        try:
            if not os.path.exists(self.arquivo_estado):
                return
            with open(self.arquivo_estado, "rb") as file_obj:
                estado = pickle.load(file_obj)

            for nome, dados in estado.get("agentes", {}).items():
                if nome not in self.agentes:
                    continue
                agente = self.agentes[nome]
                agente.peso_aprendido = dados.get("peso_aprendido", agente.peso_aprendido)
                agente.acertos = dados.get("acertos", 0)
                agente.erros = dados.get("erros", 0)
                agente.total_usos = dados.get("total_usos", 0)

            self.total_previsoes = estado.get("total_previsoes", 0)
            self.acertos = estado.get("acertos", 0)
            self.erros = estado.get("erros", 0)
            print(f"✅ Ensemble carregado: {self.acertos}/{self.total_previsoes} acertos")
        except Exception as exc:
            print(f"⚠️ Erro ao carregar ensemble: {exc}")
