"""
Indicators descobertos para o BacBo Predictor.
Esta é a base heurística usada pelos especialistas do ensemble.
"""

import random
from typing import Dict, List, Optional


class BacBoIndicators:
    """Indicadores heurísticos identificados a partir do histórico."""

    def __init__(self):
        self.LIMITE_STREAK_PLAYER = 5
        self.LIMITE_STREAK_BANKER = 4
        self.REVERSAO_APOS_3 = 0.80

        self.LIMITE_CORRECAO_INICIO = 15
        self.LIMITE_CORRECAO_GARANTIDA = 20

        self.TIE_6_PROXIMO_PLAYER = 1.0
        self.DUPLO_TIE_BANKER_PCT = 0.77
        self.VIBRACAO_DIFERENCA_1 = 0.30

        self.ALTERNANCIA_PCT = 0.60
        self.REPETICAO_PCT = 0.40

        self.SCORES_COMUNS = [6, 7, 8]

        print("✅ Indicadores BacBo carregados!")

    def detectar_padroes(self, historico: List[dict]) -> List[dict]:
        """Detecta padrões no histórico atual."""
        padroes: List[Dict[str, object]] = []

        if len(historico) < 10:
            return padroes

        streak = self._calcular_streak(historico)
        ultimo = self._ultimo_resultado(historico)

        if streak >= 3:
            if ultimo == "PLAYER":
                padroes.append(
                    {
                        "nome": "streak_3_reversao",
                        "previsao": "BANKER",
                        "confianca": min(95, 70 + streak * 5),
                        "peso_inicial": self.REVERSAO_APOS_3,
                        "detalhes": f"Streak de {streak} PLAYERs",
                    }
                )
            elif ultimo == "BANKER":
                padroes.append(
                    {
                        "nome": "streak_3_reversao",
                        "previsao": "PLAYER",
                        "confianca": min(95, 70 + streak * 5),
                        "peso_inicial": self.REVERSAO_APOS_3,
                        "detalhes": f"Streak de {streak} BANKERs",
                    }
                )

        delta = self._calcular_delta(historico)
        if abs(delta) >= self.LIMITE_CORRECAO_INICIO:
            confianca = 70 + min(25, (abs(delta) - self.LIMITE_CORRECAO_INICIO) * 2)
            padroes.append(
                {
                    "nome": "delta_correcao",
                    "previsao": "BANKER" if delta > 0 else "PLAYER",
                    "confianca": min(95, confianca),
                    "peso_inicial": 0.85,
                    "detalhes": f"Delta={delta} (correção)",
                }
            )

        if historico and historico[0].get("resultado") == "TIE":
            if (
                historico[0].get("player_score") == 6
                and historico[0].get("banker_score") == 6
            ):
                padroes.append(
                    {
                        "nome": "tie_6_player",
                        "previsao": "PLAYER",
                        "confianca": 95,
                        "peso_inicial": self.TIE_6_PROXIMO_PLAYER,
                        "detalhes": "TIE soma 6 detectado!",
                    }
                )

        if len(historico) >= 2:
            if (
                historico[0].get("resultado") == "TIE"
                and historico[1].get("resultado") == "TIE"
            ):
                padroes.append(
                    {
                        "nome": "duplo_tie_72",
                        "previsao": "BANKER",
                        "confianca": 77,
                        "peso_inicial": self.DUPLO_TIE_BANKER_PCT,
                        "detalhes": "Duplo TIE (padrão 7:2)",
                    }
                )

        if historico:
            diff = abs(
                historico[0].get("player_score", 0)
                - historico[0].get("banker_score", 0)
            )
            if diff == 1 and random.random() < self.VIBRACAO_DIFERENCA_1:
                padroes.append(
                    {
                        "nome": "vibracao_tie",
                        "previsao": "TIE",
                        "confianca": 60,
                        "peso_inicial": self.VIBRACAO_DIFERENCA_1,
                        "detalhes": "Diferença 1 → vibração para TIE",
                    }
                )

        alternancia = self._detectar_alternancia(historico)
        if alternancia:
            padroes.append(alternancia)

        return padroes

    def _calcular_streak(self, historico: List[dict]) -> int:
        streak = 0
        ultimo = None
        for rodada in historico[:10]:
            if rodada.get("resultado") != "TIE":
                if ultimo is None:
                    streak = 1
                    ultimo = rodada["resultado"]
                elif rodada["resultado"] == ultimo:
                    streak += 1
                else:
                    break
        return streak

    def _ultimo_resultado(self, historico: List[dict]) -> Optional[str]:
        for rodada in historico:
            if rodada.get("resultado") != "TIE":
                return rodada["resultado"]
        return None

    def _calcular_delta(self, historico: List[dict]) -> int:
        player = sum(1 for rodada in historico[:100] if rodada.get("resultado") == "PLAYER")
        banker = sum(1 for rodada in historico[:100] if rodada.get("resultado") == "BANKER")
        return player - banker

    def _detectar_alternancia(self, historico: List[dict]) -> Optional[dict]:
        ultimos = [r.get("resultado") for r in historico[:5] if r.get("resultado") != "TIE"]
        if len(ultimos) >= 2:
            if ultimos[0] != ultimos[1]:
                proximo = "BANKER" if ultimos[0] == "PLAYER" else "PLAYER"
                return {
                    "nome": "alternancia",
                    "previsao": proximo,
                    "confianca": 60,
                    "peso_inicial": self.ALTERNANCIA_PCT,
                    "detalhes": f"Alternando: {ultimos[0]} → {proximo}",
                }
            return {
                "nome": "repeticao",
                "previsao": ultimos[0],
                "confianca": 40,
                "peso_inicial": self.REPETICAO_PCT,
                "detalhes": f"Repetindo: {ultimos[0]}",
            }
        return None

    def analisar_somas(self, historico: List[dict]) -> Optional[dict]:
        if len(historico) < 10:
            return None

        ultimos_player = [r.get("player_score", 0) for r in historico[:20]]
        media_player = sum(ultimos_player) / len(ultimos_player)

        if media_player > 8 or media_player < 5:
            score_previsto = random.choice(self.SCORES_COMUNS)
        else:
            score_previsto = int(media_player) + random.randint(-1, 1)
            score_previsto = max(2, min(12, score_previsto))

        return {
            "player_score_previsto": score_previsto,
            "media_player": round(media_player, 1),
        }
