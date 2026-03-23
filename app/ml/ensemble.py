# app/ml/ensemble.py - VERSÃO EVOLUTIVA COM CRIAÇÃO DINÂMICA DE ESPECIALISTAS
"""
ensemble.py - Múltiplos agentes que EVOLUEM e CRIAM NOVOS ESPECIALISTAS
Começa com 7, aprende e aumenta dinamicamente
"""

import random
import pickle
import os
from collections import deque
from datetime import datetime
from typing import List, Dict, Optional
import numpy as np

from app.ml.indicators import BacBoIndicators
from app.ml.memory_map import MapaMental


class AgenteEspecialista:
    """
    Cada agente é um especialista em um tipo de padrão
    Pode ser criado, evoluir, e gerar descendentes
    """
    
    def __init__(self, nome: str, padrao_nome: str, peso_inicial: float = 0.5, geracao: int = 0):
        self.nome = nome
        self.padrao_nome = padrao_nome
        self.peso_aprendido = peso_inicial
        self.geracao = geracao
        
        # Estatísticas
        self.acertos = 0
        self.erros = 0
        self.total_usos = 0
        self.ultimo_uso = datetime.now()
        self.criado_em = datetime.now()
        
        # DNA do especialista (para crossover e mutação)
        self.dna = {
            'confianca_base': peso_inicial,
            'tendencia': random.uniform(-0.2, 0.2),  # Tendência a BANKER ou PLAYER
            'paciencia': random.uniform(0.5, 1.5),   # Quanto tempo espera antes de agir
            'agressividade': random.uniform(0.3, 1.2)  # Quão agressivo nas previsões
        }
        
        # Histórico de performance
        self.historico_precisao = deque(maxlen=100)
        self.ultimos_resultados = deque(maxlen=20)
        
        # Especialidade aprendida (pode mudar com evolução)
        self.especialidade_aprendida = None
        
        print(f"   🧬 NOVO ESPECIALISTA: {nome} (padrão: {padrao_nome}, peso: {peso_inicial:.2f}, geração: {geracao})")
    
    @property
    def precisao(self) -> float:
        total = self.acertos + self.erros
        return (self.acertos / total) if total > 0 else 0.5
    
    @property
    def peso_efetivo(self) -> float:
        """Peso ajustado pela precisão aprendida e DNA"""
        fator_dna = 1 + self.dna['tendencia'] * 0.5
        return self.peso_aprendido * (0.5 + self.precisao * 0.5) * fator_dna
    
    def registrar_resultado(self, acertou: bool, resultado_real: str = None):
        """Registra resultado e ajusta peso"""
        if acertou:
            self.acertos += 1
            # Aumenta peso se acertou
            self.peso_aprendido = min(2.5, self.peso_aprendido * 1.03)
            # Ajusta DNA baseado no sucesso
            if resultado_real:
                self.dna['tendencia'] = max(-0.3, min(0.3, 
                    self.dna['tendencia'] + (0.02 if resultado_real == 'BANKER' else -0.02)))
        else:
            self.erros += 1
            # Diminui peso se errou
            self.peso_aprendido = max(0.3, self.peso_aprendido * 0.97)
        
        self.total_usos += 1
        self.historico_precisao.append(self.precisao)
        if resultado_real:
            self.ultimos_resultados.append(resultado_real)
        self.ultimo_uso = datetime.now()
    
    def get_stats(self) -> dict:
        return {
            'nome': self.nome,
            'padrao': self.padrao_nome,
            'peso': round(self.peso_efetivo, 3),
            'acertos': self.acertos,
            'erros': self.erros,
            'total_usos': self.total_usos,
            'precisao': round(self.precisao * 100, 1),
            'geracao': self.geracao,
            'dna': self.dna,
            'especialidade': self.especialidade_aprendida or self.padrao_nome
        }
    
    def to_dict(self):
        return {
            'nome': self.nome,
            'padrao_nome': self.padrao_nome,
            'peso_aprendido': self.peso_aprendido,
            'acertos': self.acertos,
            'erros': self.erros,
            'total_usos': self.total_usos,
            'geracao': self.geracao,
            'dna': self.dna,
            'criado_em': self.criado_em.isoformat(),
            'especialidade_aprendida': self.especialidade_aprendida
        }
    
    @classmethod
    def from_dict(cls, data):
        agente = cls(
            data['nome'], 
            data['padrao_nome'], 
            data['peso_aprendido'],
            data.get('geracao', 0)
        )
        agente.acertos = data.get('acertos', 0)
        agente.erros = data.get('erros', 0)
        agente.total_usos = data.get('total_usos', 0)
        agente.dna = data.get('dna', agente.dna)
        agente.especialidade_aprendida = data.get('especialidade_aprendida')
        if 'criado_em' in data:
            agente.criado_em = datetime.fromisoformat(data['criado_em'])
        return agente
    
    @classmethod
    def criar_filho(cls, pai, mae, geracao):
        """Cria um novo especialista a partir de dois pais (crossover)"""
        nome = f"Filho_{pai.nome[:8]}_{mae.nome[:8]}_{geracao}"
        padrao = f"crossover_{pai.padrao_nome[:10]}_{mae.padrao_nome[:10]}"
        
        # Peso médio dos pais
        peso = (pai.peso_aprendido + mae.peso_aprendido) / 2
        
        filho = cls(nome, padrao, peso, geracao)
        
        # Crossover do DNA
        for key in pai.dna:
            if random.random() < 0.5:
                filho.dna[key] = pai.dna[key]
            else:
                filho.dna[key] = mae.dna[key]
        
        # Mutação
        if random.random() < 0.3:
            mutacao_key = random.choice(list(filho.dna.keys()))
            filho.dna[mutacao_key] += random.uniform(-0.1, 0.1)
            filho.dna[mutacao_key] = max(0.1, min(2.0, filho.dna[mutacao_key]))
        
        return filho
    
    @classmethod
    def criar_mutante(cls, pai, geracao):
        """Cria um mutante a partir de um pai"""
        nome = f"Mutante_{pai.nome[:8]}_{geracao}"
        padrao = f"mutacao_{pai.padrao_nome[:15]}"
        
        # Pequena variação no peso
        peso = pai.peso_aprendido * random.uniform(0.8, 1.2)
        peso = max(0.3, min(2.5, peso))
        
        mutante = cls(nome, padrao, peso, geracao)
        
        # Copiar DNA e mutar
        mutante.dna = pai.dna.copy()
        mutacao_key = random.choice(list(mutante.dna.keys()))
        mutante.dna[mutacao_key] += random.uniform(-0.2, 0.2)
        mutante.dna[mutacao_key] = max(0.1, min(2.0, mutante.dna[mutacao_key]))
        
        return mutante


class EnsembleEvolutivo:
    """
    Ensemble que EVOLUI e CRIA NOVOS ESPECIALISTAS DINAMICAMENTE
    Começa com 7 especialistas base e cresce conforme aprende
    """
    
    def __init__(self, arquivo_estado: str = 'ensemble_evolutivo.pkl'):
        self.agentes: Dict[str, AgenteEspecialista] = {}
        self.indicadores = BacBoIndicators()
        self.mapa_mental = MapaMental()
        self.arquivo_estado = arquivo_estado
        
        # Estatísticas do ensemble
        self.total_previsoes = 0
        self.acertos = 0
        self.erros = 0
        self.geracao_atual = 0
        self.historico_votacoes = deque(maxlen=200)
        
        # Controle de criação de novos agentes
        self.total_agentes_criados = 0
        self.ultima_criacao = datetime.now()
        self.criacoes_por_erro = 0
        
        # Métricas de evolução
        self.historico_populacao = deque(maxlen=50)
        self.melhores_por_geracao = []
        
        # Criar especialistas iniciais (BASE)
        self._criar_especialistas_base()
        
        # Carregar estado salvo
        self._carregar_auto()
        
        print(f"\n🎯 ENSEMBLE EVOLUTIVO INICIALIZADO!")
        print(f"   📊 {len(self.agentes)} especialistas ativos")
        print(f"   🗺️ Mapa mental: {self.mapa_mental.get_stats()['total']} memórias")
        print(f"   📈 Precisão atual: {(self.acertos/self.total_previsoes*100) if self.total_previsoes > 0 else 0:.1f}%")
    
    def _criar_especialistas_base(self):
        """Cria os 7 especialistas base (sua descoberta inicial)"""
        
        especialistas_base = [
            ('streak_3_reversao', 0.80, 'Reversão após 3+ streaks', 'streak'),
            ('delta_correcao', 0.85, 'Correção de delta', 'delta'),
            ('tie_6_player', 0.95, 'TIE 6 → PLAYER', 'tie'),
            ('duplo_tie_72', 0.77, 'Duplo TIE → BANKER', 'duplo'),
            ('vibracao_tie', 0.55, 'Vibração para TIE', 'vibracao'),
            ('alternancia', 0.60, 'Alternância', 'alternancia'),
            ('repeticao', 0.40, 'Repetição', 'repeticao')
        ]
        
        for i, (padrao, peso, desc, tipo) in enumerate(especialistas_base):
            nome = f"Base_{tipo}_{i+1}"
            self.agentes[padrao] = AgenteEspecialista(nome, padrao, peso, 0)
            print(f"   ✅ {desc}: peso {peso}")
    
    def _criar_novo_especialista_aprendido(self, contexto: List[str], previsao: str, acertou: bool):
        """
        Cria um novo especialista baseado em um padrão aprendido
        Isso acontece quando o ensemble aprende um novo padrão
        """
        self.total_agentes_criados += 1
        self.geracao_atual += 1
        
        # Criar nome baseado no contexto
        contexto_str = '_'.join(contexto[:3]) if contexto else 'novo'
        nome = f"Aprendido_{contexto_str}_{self.total_agentes_criados}"
        padrao = f"aprendido_{contexto_str}"
        
        # Peso baseado na confiança da previsão
        peso_base = 0.6 if acertou else 0.4
        
        novo_especialista = AgenteEspecialista(nome, padrao, peso_base, self.geracao_atual)
        novo_especialista.especialidade_aprendida = f"Contexto: {contexto_str}"
        
        self.agentes[padrao] = novo_especialista
        
        print(f"\n🌟 NOVO ESPECIALISTA CRIADO: {nome}")
        print(f"   📊 Padrão: {padrao}")
        print(f"   🎯 Peso inicial: {peso_base:.2f}")
        print(f"   🧬 Geração: {self.geracao_atual}")
        print(f"   🗺️ Contexto: {contexto_str}")
        
        return novo_especialista
    
    def _criar_especialista_por_crossover(self):
        """
        Cria um novo especialista por crossover dos melhores
        """
        # Pegar os melhores agentes
        melhores = sorted(
            [a for a in self.agentes.values() if a.total_usos > 20],
            key=lambda x: x.precisao,
            reverse=True
        )[:5]
        
        if len(melhores) < 2:
            return None
        
        pai = random.choice(melhores[:3])
        mae = random.choice([m for m in melhores[:3] if m.nome != pai.nome])
        
        self.total_agentes_criados += 1
        self.geracao_atual += 1
        
        filho = AgenteEspecialista.criar_filho(pai, mae, self.geracao_atual)
        filho_nome = f"Crossover_{pai.nome[:6]}_{mae.nome[:6]}_{self.total_agentes_criados}"
        filho.nome = filho_nome
        
        self.agentes[filho.padrao_nome] = filho
        
        print(f"\n🧬 NOVO ESPECIALISTA POR CROSSOVER: {filho_nome}")
        print(f"   👨 Pai: {pai.nome} (precisão: {pai.precisao*100:.1f}%)")
        print(f"   👩 Mãe: {mae.nome} (precisão: {mae.precisao*100:.1f}%)")
        
        return filho
    
    def _criar_especialista_por_mutacao(self):
        """
        Cria um novo especialista por mutação de um bom agente
        """
        # Pegar agentes com boa precisão
        bons = [a for a in self.agentes.values() if a.precisao > 0.6 and a.total_usos > 30]
        if not bons:
            return None
        
        pai = random.choice(bons)
        self.total_agentes_criados += 1
        self.geracao_atual += 1
        
        mutante = AgenteEspecialista.criar_mutante(pai, self.geracao_atual)
        mutante_nome = f"Mutante_{pai.nome[:6]}_{self.total_agentes_criados}"
        mutante.nome = mutante_nome
        
        self.agentes[mutante.padrao_nome] = mutante
        
        print(f"\n🧬 NOVO ESPECIALISTA POR MUTAÇÃO: {mutante_nome}")
        print(f"   🧬 Base: {pai.nome} (precisão: {pai.precisao*100:.1f}%)")
        
        return mutante
    
    def _criar_especialista_anti_erro(self, erro_contexto: List[str], erro_previsao: str, erro_real: str):
        """
        Cria um especialista especializado em evitar um erro específico
        """
        self.total_agentes_criados += 1
        self.geracao_atual += 1
        
        contexto_str = '_'.join(erro_contexto[:3]) if erro_contexto else 'erro'
        nome = f"AntiErro_{contexto_str}_{self.total_agentes_criados}"
        padrao = f"anti_erro_{contexto_str}"
        
        # Peso maior para evitar o erro
        peso_base = 0.7
        
        anti_erro = AgenteEspecialista(nome, padrao, peso_base, self.geracao_atual)
        anti_erro.especialidade_aprendida = f"Evitar {erro_previsao} quando {contexto_str}"
        
        # Configurar DNA para evitar o erro
        if erro_real == 'BANKER':
            anti_erro.dna['tendencia'] = 0.2  # Tendência a BANKER
        else:
            anti_erro.dna['tendencia'] = -0.2  # Tendência a PLAYER
        
        self.agentes[padrao] = anti_erro
        
        print(f"\n⚠️ NOVO ESPECIALISTA ANTI-ERRO: {nome}")
        print(f"   🎯 Especializado em evitar: {erro_previsao} → {erro_real}")
        print(f"   🗺️ Contexto: {contexto_str}")
        
        return anti_erro
    
    def _limpar_agentes_fracos(self):
        """
        Remove agentes com baixa performance para manter o ensemble eficiente
        """
        agentes_fracos = []
        for nome, agente in self.agentes.items():
            if agente.total_usos > 50 and agente.precisao < 0.45:
                agentes_fracos.append((nome, agente.precisao))
            elif agente.total_usos > 100 and agente.precisao < 0.5:
                agentes_fracos.append((nome, agente.precisao))
        
        # Ordenar por pior precisão
        agentes_fracos.sort(key=lambda x: x[1])
        
        # Remover os 20% piores, mas manter pelo menos 5 agentes
        remover = min(len(agentes_fracos) // 5, len(self.agentes) - 5)
        
        for i in range(remover):
            nome = agentes_fracos[i][0]
            if nome in self.agentes:
                print(f"   🧹 Removendo agente fraco: {nome} (precisão: {agentes_fracos[i][1]*100:.1f}%)")
                del self.agentes[nome]
        
        return remover
    
    def _evoluir_ensemble(self):
        """
        Evolui o ensemble: cria novos agentes e remove fracos
        Chamado periodicamente
        """
        print(f"\n🧬 EVOLUINDO ENSEMBLE - Geração {self.geracao_atual}")
        print(f"   👥 População atual: {len(self.agentes)} especialistas")
        
        # Remover agentes fracos
        removidos = self._limpar_agentes_fracos()
        if removidos > 0:
            print(f"   🗑️ Removidos {removidos} agentes fracos")
        
        # Criar novos agentes por crossover (se tiver agentes suficientes)
        if len(self.agentes) >= 4:
            novos_crossover = min(2, len(self.agentes) // 4)
            for _ in range(novos_crossover):
                self._criar_especialista_por_crossover()
        
        # Criar novos agentes por mutação (sempre)
        if len(self.agentes) > 5:
            self._criar_especialista_por_mutacao()
        
        # Registrar histórico
        self.historico_populacao.append({
            'geracao': self.geracao_atual,
            'total_agentes': len(self.agentes),
            'precisao_media': self.calcular_precisao_media(),
            'melhor_precisao': self.calcular_melhor_precisao()
        })
        
        print(f"   📊 Nova população: {len(self.agentes)} especialistas")
        print(f"   📈 Precisão média: {self.calcular_precisao_media()*100:.1f}%")
        print(f"   🏆 Melhor precisão: {self.calcular_melhor_precisao()*100:.1f}%")
    
    def prever(self, historico: List[dict]) -> dict:
        """
        Previsão final do ENSEMBLE EVOLUTIVO
        """
        if len(historico) < 30:
            return {
                'previsao': 'AGUARDANDO',
                'confianca': 0,
                'modo': 'INICIALIZACAO',
                'estrategias': []
            }
        
        # 1. Detectar padrões no histórico
        padroes_detectados = self.indicadores.detectar_padroes(historico)
        
        # 2. Coletar votos de TODOS os especialistas
        votos = {'BANKER': 0.0, 'PLAYER': 0.0, 'TIE': 0.0}
        votos_detalhados = []
        
        # Votos dos padrões base
        for padrao_info in padroes_detectados:
            padrao_nome = padrao_info['nome']
            if padrao_nome in self.agentes:
                especialista = self.agentes[padrao_nome]
                peso_voto = especialista.peso_efetivo * (padrao_info['confianca'] / 100)
                
                votos[padrao_info['previsao']] += peso_voto
                votos_detalhados.append({
                    'agente': especialista.nome,
                    'padrao': padrao_nome,
                    'previsao': padrao_info['previsao'],
                    'confianca': padrao_info['confianca'],
                    'peso': round(especialista.peso_efetivo, 3),
                    'detalhes': padrao_info.get('detalhes', ''),
                    'geracao': especialista.geracao
                })
        
        # 3. Votos de TODOS os agentes aprendidos (não apenas padrões base)
        for nome, agente in self.agentes.items():
            if agente.padrao_nome not in [p['nome'] for p in padroes_detectados]:
                # Agentes aprendidos podem votar baseado em seu DNA
                # Eles têm uma "opinião" baseada em sua especialidade
                if agente.total_usos > 10:  # Só votam se tiverem experiência
                    confianca_agente = agente.precisao * 0.7 + 0.3
                    tendencia = agente.dna['tendencia']
                    
                    # Decisão baseada no DNA
                    if tendencia > 0.1:
                        previsao = 'BANKER'
                    elif tendencia < -0.1:
                        previsao = 'PLAYER'
                    else:
                        previsao = random.choice(['BANKER', 'PLAYER'])
                    
                    peso_voto = agente.peso_efetivo * confianca_agente * 0.5
                    votos[previsao] += peso_voto
                    votos_detalhados.append({
                        'agente': agente.nome,
                        'padrao': agente.padrao_nome,
                        'previsao': previsao,
                        'confianca': round(confianca_agente * 100, 1),
                        'peso': round(agente.peso_efetivo, 3),
                        'geracao': agente.geracao
                    })
        
        # 4. Consultar mapa mental
        contexto = [r.get('resultado') for r in historico[:10] if r.get('resultado') != 'TIE'][:5]
        memorias = self.mapa_mental.consultar(contexto, limite=5)
        
        for memoria in memorias:
            peso_memoria = memoria.peso * 0.6
            votos[memoria.previsao] += peso_memoria
            votos_detalhados.append({
                'agente': 'MEMORIA',
                'padrao': memoria.padrao,
                'previsao': memoria.previsao,
                'confianca': round(memoria.precisao * 100, 1),
                'peso': round(memoria.peso, 3)
            })
        
        # 5. Decisão final
        total_votos = sum(votos.values())
        if total_votos > 0:
            previsao_final = max(votos, key=votos.get)
            confianca = (votos[previsao_final] / total_votos) * 100
        else:
            # Fallback
            ultimos = [r.get('resultado') for r in historico[:20] if r.get('resultado') != 'TIE']
            if ultimos:
                banker = ultimos.count('BANKER')
                player = ultimos.count('PLAYER')
                previsao_final = 'BANKER' if banker > player else 'PLAYER'
                confianca = 55
            else:
                previsao_final = random.choice(['BANKER', 'PLAYER'])
                confianca = 50
        
        # Guardar para aprendizado
        self._ultimo_contexto = contexto
        self._ultimos_padroes = padroes_detectados
        self._ultimas_memorias = memorias
        self._ultima_previsao = previsao_final
        self._ultimos_votos = votos_detalhados
        self._ultimo_historico = historico
        
        # Preparar estratégias para o frontend
        estrategias = []
        for v in votos_detalhados[:10]:
            if v['agente'] != 'MEMORIA':
                estrategias.append(f"{v['padrao']}({v['confianca']:.0f}%)")
        
        return {
            'previsao': previsao_final,
            'simbolo': '🔴' if previsao_final == 'BANKER' else '🔵',
            'confianca': round(confianca),
            'modo': 'ENSEMBLE_EVOLUTIVO',
            'estrategias': estrategias[:8],
            'especialistas_ativos': len([v for v in votos_detalhados if v['agente'] != 'MEMORIA']),
            'memorias_ativas': len(memorias),
            'total_votos': len(votos_detalhados),
            'total_agentes': len(self.agentes),
            'geracao': self.geracao_atual
        }
    
    def aprender(self, resultado_real: str):
        """
        ENSEMBLE aprende com o resultado real
        Pode criar novos especialistas baseado no erro
        """
        if not hasattr(self, '_ultima_previsao'):
            return False
        
        acertou = (self._ultima_previsao == resultado_real)
        
        # Atualizar estatísticas
        self.total_previsoes += 1
        if acertou:
            self.acertos += 1
        else:
            self.erros += 1
        
        # 1. Atualizar especialistas que participaram
        for padrao_info in getattr(self, '_ultimos_padroes', []):
            padrao_nome = padrao_info['nome']
            if padrao_nome in self.agentes:
                especialista = self.agentes[padrao_nome]
                acertou_padrao = (padrao_info['previsao'] == resultado_real)
                especialista.registrar_resultado(acertou_padrao, resultado_real)
        
        # 2. Atualizar TODOS os agentes aprendidos (aprendizado em lote)
        for nome, agente in self.agentes.items():
            if agente.total_usos > 0:
                # Cada agente aprende baseado no seu DNA
                tendencia = agente.dna['tendencia']
                if tendencia > 0.1:
                    previsao_agente = 'BANKER'
                elif tendencia < -0.1:
                    previsao_agente = 'PLAYER'
                else:
                    previsao_agente = random.choice(['BANKER', 'PLAYER'])
                
                acertou_agente = (previsao_agente == resultado_real)
                agente.registrar_resultado(acertou_agente, resultado_real)
        
        # 3. Atualizar mapa mental
        for memoria in getattr(self, '_ultimas_memorias', []):
            acertou_memoria = (memoria.previsao == resultado_real)
            self.mapa_mental.atualizar_memoria(memoria.id, acertou_memoria)
        
        # 4. CRIAR NOVOS ESPECIALISTAS quando aprender novos padrões
        if acertou:
            # Acertou: pode criar um novo especialista baseado no contexto (se for padrão novo)
            contexto_str = '_'.join(self._ultimo_contexto[:3]) if self._ultimo_contexto else 'novo'
            padrao_novo = f"aprendido_{contexto_str}"
            
            if padrao_novo not in self.agentes:
                self._criar_novo_especialista_aprendido(
                    self._ultimo_contexto,
                    self._ultima_previsao,
                    acertou
                )
        
        else:
            # ERROU: criar especialista anti-erro!
            self.criacoes_por_erro += 1
            self._criar_especialista_anti_erro(
                self._ultimo_contexto,
                self._ultima_previsao,
                resultado_real
            )
        
        # 5. Evoluir ensemble periodicamente
        if self.total_previsoes % 50 == 0:
            self._evoluir_ensemble()
        
        # Salvar automaticamente
        if self.total_previsoes % 20 == 0:
            self._salvar_auto()
        
        return acertou
    
    def calcular_precisao_media(self) -> float:
        """Calcula precisão média de todos os agentes"""
        if not self.agentes:
            return 0
        precisoes = [a.precisao for a in self.agentes.values() if a.total_usos > 10]
        return sum(precisoes) / len(precisoes) if precisoes else 0
    
    def calcular_melhor_precisao(self) -> float:
        """Retorna a melhor precisão entre os agentes"""
        if not self.agentes:
            return 0
        return max([a.precisao for a in self.agentes.values() if a.total_usos > 10] or [0])
    
    def get_stats(self) -> dict:
        """Retorna estatísticas do ensemble evolutivo"""
        precisao = (self.acertos / self.total_previsoes * 100) if self.total_previsoes > 0 else 0
        
        especialistas_stats = []
        for nome, agente in self.agentes.items():
            stats = agente.get_stats()
            especialistas_stats.append(stats)
        
        # Estatísticas de evolução
        evolucao_stats = {
            'total_agentes': len(self.agentes),
            'geracao_atual': self.geracao_atual,
            'total_agentes_criados': self.total_agentes_criados,
            'criacoes_por_erro': self.criacoes_por_erro,
            'historico_populacao': list(self.historico_populacao),
            'precisao_media_agentes': round(self.calcular_precisao_media() * 100, 1),
            'melhor_precisao_agente': round(self.calcular_melhor_precisao() * 100, 1)
        }
        
        return {
            'total_previsoes': self.total_previsoes,
            'acertos': self.acertos,
            'erros': self.erros,
            'precisao': round(precisao, 1),
            'especialistas': sorted(especialistas_stats, key=lambda x: x['precisao'], reverse=True),
            'mapa_mental': self.mapa_mental.get_stats(),
            'evolucao': evolucao_stats,
            'total_agentes': len(self.agentes)
        }
    
    def _salvar_auto(self):
        """Salva estado do ensemble evolutivo"""
        try:
            estado = {
                'agentes': {nome: agente.to_dict() for nome, agente in self.agentes.items()},
                'total_previsoes': self.total_previsoes,
                'acertos': self.acertos,
                'erros': self.erros,
                'geracao_atual': self.geracao_atual,
                'total_agentes_criados': self.total_agentes_criados,
                'criacoes_por_erro': self.criacoes_por_erro,
                'historico_populacao': list(self.historico_populacao)
            }
            with open(self.arquivo_estado, 'wb') as f:
                pickle.dump(estado, f)
        except Exception as e:
            print(f"⚠️ Erro ao salvar ensemble: {e}")
    
    def _carregar_auto(self):
        """Carrega estado do ensemble evolutivo"""
        try:
            if os.path.exists(self.arquivo_estado):
                with open(self.arquivo_estado, 'rb') as f:
                    estado = pickle.load(f)
                
                for nome, dados in estado.get('agentes', {}).items():
                    self.agentes[nome] = AgenteEspecialista.from_dict(dados)
                
                self.total_previsoes = estado.get('total_previsoes', 0)
                self.acertos = estado.get('acertos', 0)
                self.erros = estado.get('erros', 0)
                self.geracao_atual = estado.get('geracao_atual', 0)
                self.total_agentes_criados = estado.get('total_agentes_criados', 0)
                self.criacoes_por_erro = estado.get('criacoes_por_erro', 0)
                self.historico_populacao = deque(estado.get('historico_populacao', []), maxlen=50)
                
                print(f"✅ Ensemble evolutivo carregado: {len(self.agentes)} agentes")
                print(f"   📊 Geração: {self.geracao_atual}")
                print(f"   🧬 Total criados: {self.total_agentes_criados}")
        except Exception as e:
            print(f"⚠️ Erro ao carregar ensemble: {e}")
