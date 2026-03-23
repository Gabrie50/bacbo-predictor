"""Simulador de cenários para treino do ensemble."""

import random
from typing import List, Tuple


class SimuladorCenarios:
    """Simula cenários usando as probabilidades heurísticas do projeto."""

    def __init__(self):
        self.probabilidade_algoritmo = {
            "reversao_streak": 0.80,
            "delta_correcao": 0.85,
            "tie_6_player": 0.95,
            "duplo_tie_banker": 0.77,
            "alternancia": 0.60,
            "repeticao": 0.40,
        }
        print("🎲 Simulador de Cenários inicializado")

    def gerar_historico_simulado(self, tamanho: int = 50) -> List[dict]:
        historico = []
        ultimo_resultado = None
        streak = 0
        delta = 0

        for _ in range(tamanho):
            if streak >= 3:
                if random.random() < self.probabilidade_algoritmo["reversao_streak"]:
                    resultado = "BANKER" if ultimo_resultado == "PLAYER" else "PLAYER"
                else:
                    resultado = ultimo_resultado
            elif abs(delta) > 15:
                if random.random() < self.probabilidade_algoritmo["delta_correcao"]:
                    resultado = "BANKER" if delta > 0 else "PLAYER"
                else:
                    resultado = "PLAYER" if delta > 0 else "BANKER"
            else:
                if ultimo_resultado:
                    if random.random() < self.probabilidade_algoritmo["alternancia"]:
                        resultado = "BANKER" if ultimo_resultado == "PLAYER" else "PLAYER"
                    else:
                        resultado = ultimo_resultado
                else:
                    resultado = random.choice(["BANKER", "PLAYER"])

            if resultado == "PLAYER":
                player_score = random.randint(5, 9)
                banker_score = random.randint(2, player_score - 1)
            elif resultado == "BANKER":
                banker_score = random.randint(5, 9)
                player_score = random.randint(2, banker_score - 1)
            else:
                soma = random.choice([6, 7, 8])
                player_score = soma
                banker_score = soma

            rodada = {
                "resultado": resultado,
                "player_score": player_score,
                "banker_score": banker_score,
                "soma": player_score + banker_score,
            }
            historico.insert(0, rodada)

            if resultado != "TIE":
                streak = streak + 1 if resultado == ultimo_resultado else 1
                ultimo_resultado = resultado
                delta += 1 if resultado == "PLAYER" else -1
            else:
                streak = 0

        return historico

    def gerar_episodio_treinamento(self, num_rodadas: int = 100) -> List[Tuple[List[dict], str]]:
        episodio = []
        historico = self.gerar_historico_simulado(50)
        for _ in range(num_rodadas):
            proxima = self._gerar_proxima_rodada(historico)
            episodio.append((historico.copy(), proxima["resultado"]))
            historico.insert(0, proxima)
        return episodio

    def _gerar_proxima_rodada(self, historico: List[dict]) -> dict:
        if len(historico) < 10:
            resultado = random.choice(["BANKER", "PLAYER"])
        else:
            ultimos = [r["resultado"] for r in historico[:10] if r["resultado"] != "TIE"]
            streak = self._calcular_streak(ultimos)
            delta = self._calcular_delta(historico)

            if streak >= 3:
                if random.random() < self.probabilidade_algoritmo["reversao_streak"]:
                    resultado = "BANKER" if ultimos[0] == "PLAYER" else "PLAYER"
                else:
                    resultado = ultimos[0]
            elif abs(delta) > 15:
                if random.random() < self.probabilidade_algoritmo["delta_correcao"]:
                    resultado = "BANKER" if delta > 0 else "PLAYER"
                else:
                    resultado = "PLAYER" if delta > 0 else "BANKER"
            elif historico[0].get("resultado") == "TIE" and historico[0].get("player_score") == 6:
                if random.random() < self.probabilidade_algoritmo["tie_6_player"]:
                    resultado = "PLAYER"
                else:
                    resultado = random.choice(["BANKER", "PLAYER"])
            elif len(historico) >= 2 and historico[0]["resultado"] == "TIE" and historico[1]["resultado"] == "TIE":
                if random.random() < self.probabilidade_algoritmo["duplo_tie_banker"]:
                    resultado = "BANKER"
                else:
                    resultado = "PLAYER"
            else:
                if ultimos and random.random() < self.probabilidade_algoritmo["alternancia"]:
                    resultado = "BANKER" if ultimos[0] == "PLAYER" else "PLAYER"
                elif ultimos:
                    resultado = ultimos[0]
                else:
                    resultado = random.choice(["BANKER", "PLAYER"])

        if resultado == "PLAYER":
            player_score = random.randint(5, 9)
            banker_score = random.randint(2, player_score - 1)
        elif resultado == "BANKER":
            banker_score = random.randint(5, 9)
            player_score = random.randint(2, banker_score - 1)
        else:
            soma = random.choice([6, 7, 8])
            player_score = soma
            banker_score = soma

        return {
            "resultado": resultado,
            "player_score": player_score,
            "banker_score": banker_score,
            "soma": player_score + banker_score,
        }

    def _calcular_streak(self, ultimos: List[str]) -> int:
        if not ultimos:
            return 0
        streak = 1
        for i in range(1, len(ultimos)):
            if ultimos[i] == ultimos[0]:
                streak += 1
            else:
                break
        return streak

    def _calcular_delta(self, historico: List[dict]) -> int:
        player = sum(1 for r in historico[:100] if r["resultado"] == "PLAYER")
        banker = sum(1 for r in historico[:100] if r["resultado"] == "BANKER")
        return player - banker

    def treinar_agente(self, agente, num_episodios: int = 10, rodadas_por_episodio: int = 100):
        print("\n🎲 TREINANDO AGENTE POR SIMULAÇÃO")
        print(f"   Episódios: {num_episodios}")
        print(f"   Rodadas por episódio: {rodadas_por_episodio}")

        acertos_totais = 0
        total_rodadas = 0
        for episodio_idx in range(num_episodios):
            episodio = self.gerar_episodio_treinamento(rodadas_por_episodio)
            acertos_episodio = 0
            for contexto, resultado_real in episodio:
                previsao = agente.prever(contexto)
                if previsao["previsao"] != "AGUARDANDO":
                    if agente.aprender(resultado_real):
                        acertos_episodio += 1
                    total_rodadas += 1
            acertos_totais += acertos_episodio
            precisao = (acertos_episodio / rodadas_por_episodio) * 100
            print(f"   Episódio {episodio_idx + 1}: {acertos_episodio}/{rodadas_por_episodio} ({precisao:.1f}%)")

        if total_rodadas > 0:
            precisao_final = (acertos_totais / total_rodadas) * 100
            print(f"\n✅ Treinamento concluído! Precisão final: {precisao_final:.1f}%")

        return acertos_totais, total_rodadas
