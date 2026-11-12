"""Regras de Tormenta 20 (Edição Jogo do Ano) portadas do bot `artoniana`.

Código copiado de github.com/RamonCout0/artoniana (bot.py) — tabelas e funções
puras, sem nada de Discord. Se o artoniana mudar, rode de novo o porte.

Referências: clima p.267 · terrenos p.264-266 · viagens Tabela 6-4 p.270 ·
armaduras/escudos mágicos p.338-340 (Tabelas 8-4, 8-10 e 8-11).
"""
import random
import re
from collections import namedtuple

Choice = namedtuple("Choice", "name value")


class app_commands:  # só pra manter as listas *_CHOICES idênticas ao original
    Choice = Choice

# ---------------------------------------------------------------------------
# Clima (p.267)
# ---------------------------------------------------------------------------

CLIMA_NOTAS = {
    'ensolarado': 'Clima bom. Sem modificadores e sem redução na distância de viagem.',
    'calor': 'Clima muito quente (acima de 50 °C). Teste de Fortitude por **dia** '
             '(CD 15 +1 por teste anterior). Se falhar, sofre 1d6 pontos de dano de fogo, '
             'que só pode ser curado depois de sair do clima quente.',
    'calor extremo': 'Calor extremo (acima de 60 °C). Teste de Fortitude por **minuto** '
                     '(CD 15 +1 por teste anterior). Se falhar, sofre 1d6 pontos de dano de fogo, '
                     'que só pode ser curado depois de sair do clima quente.',
    'frio': 'Clima muito frio (abaixo de –10 °C). Teste de Fortitude por **dia** '
            '(CD 15 +1 por teste anterior). Se falhar, sofre 1d6 pontos de dano de frio, '
            'que só pode ser curado depois de sair do clima frio.',
    'frio extremo': 'Frio extremo (abaixo de –20 °C). Teste de Fortitude por **minuto** '
                    '(CD 15 +1 por teste anterior). Se falhar, sofre 1d6 pontos de dano de frio, '
                    'que só pode ser curado depois de sair do clima frio.',
    'neblina': 'Fornece camuflagem. Neblina **espessa** fornece camuflagem leve a criaturas '
               'a 1,5m e camuflagem total a criaturas a mais de 1,5m.',
    'chuva': '–5 em testes de Percepção e os mesmos efeitos de vento forte.',
    'granizo': 'Como chuva, mas no início de cada rodada todas as criaturas sofrem '
               '1 ponto de dano de impacto.',
    'neve': 'Como chuva, mas cria terreno difícil.',
    'tempestade': '–10 em testes de Percepção e os mesmos efeitos de vendaval. No início de cada '
                  'rodada, há 10% de chance de uma criatura aleatória ser atingida por um raio '
                  '(8d10 pontos de dano de eletricidade).',
    'vento forte': '–2 em testes de ataque à distância e 50% de chance por rodada de apagar '
                   'chamas ou dissipar névoas.',
    'vendaval': '–5 em testes de ataque à distância. Apaga chamas e dissipa névoas.',
    'furacao': 'Torna ataques à distância impossíveis, apaga chamas e dissipa névoas. No início '
               'de cada rodada, criaturas Médias ou menores devem passar em um teste de Fortitude '
               '(CD 15) ou caem, são arrastadas 1d4 x 1,5m na direção do vento e sofrem 1d6 pontos '
               'de dano de impacto para cada 1,5m.',
    'tornado': 'Torna ataques à distância impossíveis, apaga chamas e dissipa névoas. No início de '
               'cada rodada, criaturas Grandes ou menores devem passar em um teste de Fortitude '
               '(CD 25) ou caem, são arrastadas 1d12 x 1,5m em uma direção aleatória e sofrem '
               '1d6 pontos de dano de impacto para cada 1,5m.',
}

# Climas coerentes por terreno. Não é regra do livro: é curadoria para o gerador
# não sortear "neve no deserto".
ALLOWED_CLIMES = {
    None: list(CLIMA_NOTAS),
    'colinas': ['ensolarado', 'chuva', 'neblina', 'granizo', 'tempestade', 'vento forte', 'vendaval'],
    'desertos': ['ensolarado', 'calor', 'calor extremo', 'tempestade', 'vento forte', 'vendaval'],
    'florestas': ['ensolarado', 'chuva', 'neblina', 'granizo', 'tempestade', 'vento forte'],
    'montanhas': ['ensolarado', 'neblina', 'neve', 'frio', 'frio extremo', 'granizo',
                  'tempestade', 'vento forte', 'vendaval'],
    'pantanos': ['ensolarado', 'chuva', 'neblina', 'calor', 'tempestade'],
    'planicies': ['ensolarado', 'chuva', 'neblina', 'granizo', 'tempestade', 'vento forte',
                  'vendaval', 'furacao', 'tornado'],
    'artico': ['neve', 'frio', 'frio extremo', 'neblina', 'vento forte', 'vendaval'],
    'aquatico': ['ensolarado', 'chuva', 'neblina', 'tempestade', 'vento forte', 'vendaval', 'furacao'],
}

# ---------------------------------------------------------------------------
# Terrenos (p.264-266)
# ---------------------------------------------------------------------------

TERRENOS = {
    'colinas': [
        ('Inclinação Suave', 'Não afeta o movimento, mas personagens no lado superior recebem '
                             'bônus por terreno elevado contra personagens no lado inferior.'),
        ('Inclinação Íngreme', 'Conta como terreno difícil para subir. Descer correndo ou fazendo '
                               'uma investida exige um teste de Acrobacia (ou Cavalgar, se montado; '
                               'CD 10). Em caso de falha, você cai no chão, rola 1d4 x 1,5m para '
                               'frente e sofre 1d6 pontos de dano de impacto por 1,5m rolados.'),
        ('Penhasco', 'Tem 1d6 x 3m de altura. Escalar exige um teste de Atletismo (CD 15).'),
    ],
    'desertos': [
        ('Dunas', 'Funcionam como inclinações íngremes (veja Colinas). Porém, cair e rolar de uma '
                  'duna não causa dano.'),
        ('Observação', 'Desertos são áridos e quentes. Para desertos de clima frio, use o terreno '
                       '**ártico**. O calor em si é tratado pelo clima (`/clima`), não pelo terreno.'),
    ],
    'florestas': [
        ('Árvores', 'Estreitas (menos de 1,5m): RD 5, 100 PV, permitem ficar no mesmo espaço com '
                    'cobertura leve. Largas (mais de 1,5m): RD 5, 500 PV, cobertura leve atrás '
                    'delas. Subir exige Atletismo (CD 15); no topo é preciso se equilibrar (CD 15). '
                    'No topo de uma árvore larga você recebe camuflagem leve contra criaturas no solo.'),
        ('Folhagens', 'Moitas e arbustos contam como terreno difícil e fornecem camuflagem leve a '
                      'criaturas dentro deles.'),
        ('Vegetação Rasteira', 'Conta como terreno difícil e impõe –2 em testes de Furtividade.'),
    ],
    'montanhas': [
        ('Abismo', 'Fenda com 1d4 x 1,5m de largura e 2d4 x 3m de profundidade. Escalar para fora '
                   'exige Atletismo (CD 20).'),
        ('Altitude', 'No cume, um teste de Fortitude por dia (CD 15 +1 por teste anterior). Em caso '
                     'de falha, fica fatigado até descer (ou exausto, se já estava fatigado).'),
        ('Paredão', 'Penhasco vertical com 2d6 x 3m de altura. Escalar exige Atletismo (CD 25).'),
        ('Seixos', 'Inclinações íngremes cobertas de pedrinhas: a CD para descer numa corrida ou '
                   'investida aumenta para 15.'),
        ('Também aplica', 'Inclinações e penhascos, como em Colinas.'),
    ],
    'pantanos': [
        ('Lodaçal', 'Conta como terreno difícil e impõe a condição **vulnerável** a qualquer '
                    'personagem dentro dele.'),
        ('Também aplica', 'Vegetação rasteira, folhagens e árvores (veja Florestas) e água parada '
                          '(veja Aquático).'),
    ],
    'planicies': [
        ('Sem elementos', 'Normalmente não há elementos associados a planícies, embora às vezes '
                          'contenham vegetação rasteira (veja Florestas).'),
        ('Trincheira', 'Um personagem em uma trincheira recebe cobertura leve contra ataques à '
                       'distância. Sair de uma trincheira conta como terreno difícil. Vale também '
                       'para valas e leitos de rio secos.'),
    ],
    'artico': [
        ('Gelo', 'Você pode andar no gelo à metade do deslocamento sem testes. Andar no deslocamento '
                 'normal, correr, investir ou sofrer dano exige Acrobacia (CD 15 para movimento, ou '
                 'igual ao dano sofrido). Em caso de falha, você cai e desliza 1d4 x 1,5m.'),
        ('Rio Congelado', 'Como andar sobre gelo. Se cair e rolar 1 no d4, o gelo quebra e você '
                          'afunda: sofre 1d6 pontos de dano de frio por rodada e precisa nadar. '
                          'Abrir um buraco exige causar 10 pontos de dano de impacto ou fogo.'),
    ],
    'aquatico': [
        ('Água Corrente', 'Correnteza típica de 1d6 x 3m por rodada; no fim de cada rodada todos na '
                          'água são arrastados nessa velocidade. Nadar exige Atletismo CD 15 (até 9m '
                          'por rodada) ou CD 20 (mais rápido). Sair de uma correnteza de 15m ou mais '
                          'exige chegar a um apoio, gastar uma ação de movimento e passar em '
                          'Atletismo (CD 20).'),
        ('Água Parada', 'Exige testes de Atletismo para nadar conforme a perícia, sem outros '
                        'modificadores.'),
        ('Personagens Submersos', 'Não podem falar (nem lançar magias), sofrem –2 em ataque e –5 em '
                                  'Percepção e só se deslocam nadando. Armas à distância não podem '
                                  'ser usadas (exceto armas de arremesso de perfuração, bestas e '
                                  'redes); armas de corte e impacto causam metade do dano. Criaturas '
                                  'submersas recebem camuflagem e cobertura leves contra quem está '
                                  'fora d\'água.'),
    ],
}

TERRENO_CHOICES = [
    Choice(name='Colinas', value='colinas'),
    Choice(name='Desertos', value='desertos'),
    Choice(name='Florestas', value='florestas'),
    Choice(name='Montanhas', value='montanhas'),
    Choice(name='Pântanos', value='pantanos'),
    Choice(name='Planícies', value='planicies'),
    Choice(name='Ártico', value='artico'),
    Choice(name='Aquático', value='aquatico'),
]

CLIMA_CHOICES = [
    Choice(name='Ensolarado', value='ensolarado'),
    Choice(name='Calor (acima de 50 °C)', value='calor'),
    Choice(name='Calor extremo (acima de 60 °C)', value='calor extremo'),
    Choice(name='Frio (abaixo de -10 °C)', value='frio'),
    Choice(name='Frio extremo (abaixo de -20 °C)', value='frio extremo'),
    Choice(name='Neblina', value='neblina'),
    Choice(name='Chuva', value='chuva'),
    Choice(name='Granizo', value='granizo'),
    Choice(name='Neve', value='neve'),
    Choice(name='Tempestade', value='tempestade'),
    Choice(name='Vento forte', value='vento forte'),
    Choice(name='Vendaval', value='vendaval'),
    Choice(name='Furacão', value='furacao'),
    Choice(name='Tornado', value='tornado'),
]

NOME_BONITO = {c.value: c.name for c in TERRENO_CHOICES}
NOME_BONITO.update({c.value: c.name for c in CLIMA_CHOICES})


def rotulo(valor):
    if not valor:
        return 'não definido'
    return NOME_BONITO.get(valor, valor)


# ---------------------------------------------------------------------------
# Tabela 8-4: armaduras e escudos (p.331)
# ---------------------------------------------------------------------------

TABELA_8_4_ARMADURAS = [
    {'faixa': (1, 5), 'nome': 'Couro', 'escudo': False},
    {'faixa': (6, 10), 'nome': 'Brunea', 'escudo': False},
    {'faixa': (11, 25), 'nome': 'Completa', 'escudo': False},
    {'faixa': (26, 30), 'nome': 'Cota de malha', 'escudo': False},
    {'faixa': (31, 45), 'nome': 'Couraça', 'escudo': False},
    {'faixa': (46, 55), 'nome': 'Couro batido', 'escudo': False},
    {'faixa': (56, 65), 'nome': 'Escudo leve', 'escudo': True},
    {'faixa': (66, 80), 'nome': 'Escudo pesado', 'escudo': True},
    {'faixa': (81, 85), 'nome': 'Gibão de peles', 'escudo': False},
    {'faixa': (86, 90), 'nome': 'Loriga segmentada', 'escudo': False},
    {'faixa': (91, 100), 'nome': 'Meia armadura', 'escudo': False},
]

# ---------------------------------------------------------------------------
# Tabela 8-10: encantos de armaduras e escudos (p.339)
# ---------------------------------------------------------------------------

TABELA_8_10_ENCANTOS = [
    {'faixa': (1, 6), 'nome': 'Abascanto', 'efeito': 'Resistência contra magia',
     'descricao': 'Você recebe resistência a magia +5.'},
    {'faixa': (7, 10), 'nome': 'Abençoado', 'efeito': 'Resistência contra trevas',
     'descricao': 'Você recebe redução de trevas 10 e +5 em testes de resistência contra efeitos '
                  'de necromancia.'},
    {'faixa': (11, 12), 'nome': 'Acrobático', 'efeito': 'Bônus em Acrobacia',
     'descricao': 'Você recebe +5 em Acrobacia e ignora a penalidade de armadura do item para '
                  'testes dessa perícia.'},
    {'faixa': (13, 14), 'nome': 'Alado', 'efeito': 'Deslocamento de voo 12m',
     'descricao': 'Você pode gastar 2 PM para fazer asas emergirem de suas costas e receber '
                  'deslocamento de voo 12m com duração sustentada.'},
    {'faixa': (15, 16), 'nome': 'Animado', 'efeito': 'Escudo defende sozinho', 'apenas_escudo': True,
     'descricao': 'Você pode gastar uma ação de movimento e 1 PM para fazer o escudo flutuar ao seu '
                  'redor até o fim da cena, mantendo o bônus na Defesa com as duas mãos livres.'},
    {'faixa': (17, 18), 'nome': 'Assustador', 'efeito': 'Causa efeito de medo',
     'descricao': 'Ação de movimento e 2 PM: inimigos em alcance curto devem passar num teste de '
                  'Vontade (CD Car) ou ficarão abalados até o fim da cena.'},
    {'faixa': (19, 22), 'nome': 'Cáustica', 'efeito': 'Resistência contra ácido',
     'descricao': 'Você recebe redução de ácido 10 e pode gastar uma ação de movimento e 2 PM para '
                  'que seus ataques causem +1d4 de dano de ácido até o fim da cena.'},
    {'faixa': (23, 32), 'nome': 'Defensor', 'efeito': 'Defesa +2',
     'descricao': 'O bônus na Defesa do item aumenta em +2.'},
    {'faixa': (33, 34), 'nome': 'Escorregadio', 'efeito': 'Bônus para escapar',
     'descricao': 'Você recebe +10 em testes de Acrobacia para escapar e em testes de manobra '
                  'contra agarrar.'},
    {'faixa': (35, 36), 'nome': 'Esmagador', 'efeito': 'Escudo causa mais dano', 'apenas_escudo': True,
     'descricao': 'Este escudo fornece +2 em ataques e dano e tem seu dano aumentado em um passo.'},
    {'faixa': (37, 38), 'nome': 'Fantasmagórico', 'efeito': 'Lança Manto de Sombras',
     'descricao': 'Você pode lançar a magia Manto de Sombras.'},
    {'faixa': (39, 40), 'nome': 'Fortificado', 'efeito': 'Chance de ignorar crítico',
     'descricao': 'Você recebe 25% de chance (escudos) ou 50% de chance (armaduras) de ignorar o '
                  'dano extra de acertos críticos e ataques furtivos.'},
    {'faixa': (41, 44), 'nome': 'Gélido', 'efeito': 'Resistência contra frio',
     'descricao': 'Você recebe redução de frio 10 e pode gastar uma ação de movimento e 2 PM para '
                  'se cobrir de gelo até o fim da cena, recebendo 10 PV temporários.'},
    {'faixa': (45, 54), 'nome': 'Guardião', 'efeito': 'Defesa +4', 'vale_dois': True,
     'descricao': 'O bônus na Defesa do item aumenta em +4. Pré-requisito: defensor.'},
    {'faixa': (55, 56), 'nome': 'Hipnótico', 'efeito': 'Fascina inimigos',
     'descricao': 'Ação padrão e 3 PM: inimigos em alcance curto devem passar num teste de Vontade '
                  '(CD Car) ou ficarão fascinados por 1d6 rodadas. O efeito termina se qualquer '
                  'criatura afetada for atacada.'},
    {'faixa': (57, 58), 'nome': 'Ilusório', 'efeito': 'Camufla-se como item comum',
     'descricao': 'Ação de movimento e 1 PM: o item adquire a aparência de uma roupa comum, mas '
                  'mantém suas propriedades. Visão da Verdade revela o disfarce.'},
    {'faixa': (59, 62), 'nome': 'Incandescente', 'efeito': 'Resistência contra fogo',
     'descricao': 'Você recebe redução de fogo 10 e pode gastar uma ação de movimento e 2 PM para o '
                  'item emitir labaredas até o fim da cena, causando 1d6 de dano de fogo em '
                  'criaturas adjacentes no início de cada um de seus turnos.'},
    {'faixa': (63, 68), 'nome': 'Invulnerável', 'efeito': 'Redução de dano',
     'descricao': 'Você recebe redução de dano 2 (escudos) ou 5 (armaduras).'},
    {'faixa': (69, 72), 'nome': 'Opaco', 'efeito': 'Redução de energia',
     'descricao': 'Você recebe redução de ácido, eletricidade, fogo e frio 10.'},
    {'faixa': (73, 78), 'nome': 'Protetor', 'efeito': 'Resistência +2',
     'descricao': 'Você recebe +2 em testes de resistência.'},
    {'faixa': (79, 80), 'nome': 'Refletor', 'efeito': 'Reflete magia',
     'descricao': 'Uma vez por rodada, quando você é alvo de uma magia, pode gastar PM igual ao '
                  'custo dela para refleti-la de volta ao conjurador.'},
    {'faixa': (81, 84), 'nome': 'Relampejante', 'efeito': 'Resistência contra eletricidade',
     'descricao': 'Você recebe redução de eletricidade 10 e pode gastar uma ação de movimento e '
                  '2 PM para gerar arcos voltaicos até o fim da cena: quem o atacar em corpo a '
                  'corpo sofre 2d6 pontos de dano de eletricidade.'},
    {'faixa': (85, 86), 'nome': 'Reluzente', 'efeito': 'Causa efeito de cegueira',
     'descricao': 'Ação de movimento e 2 PM: inimigos em alcance curto devem passar num teste de '
                  'Reflexos (CD Car) ou ficarão cegos por uma rodada.'},
    {'faixa': (87, 88), 'nome': 'Sombrio', 'efeito': 'Bônus em Furtividade',
     'descricao': 'Você recebe +5 em Furtividade e ignora a penalidade de armadura do item para '
                  'testes dessa perícia.'},
    {'faixa': (89, 90), 'nome': 'Zeloso', 'efeito': 'Atrai ataques em aliados',
     'descricao': 'Uma vez por rodada, se um aliado adjacente for alvo de um ataque, você pode '
                  'gastar 1 PM para se tornar o alvo do ataque.'},
    {'faixa': (91, 100), 'nome': 'Item específico', 'efeito': 'Veja a Tabela 8-11',
     'especifico': True, 'descricao': 'Role na Tabela 8-11. O item perde quaisquer encantos rolados.'},
]

# ---------------------------------------------------------------------------
# Tabela 8-11: armaduras e escudos específicos (p.340)
# ---------------------------------------------------------------------------

TABELA_8_11_ESPECIFICOS = [
    {'faixa': (1, 10), 'nome': 'Cota élfica', 'preco': 'T$ 30.000', 'escudo': False,
     'descricao': 'Cota de malha defensora de mitral. Permite aplicar sua Destreza na Defesa como '
                  'se fosse uma armadura leve.'},
    {'faixa': (11, 20), 'nome': 'Couro de monstro', 'preco': 'T$ 36.000', 'escudo': False,
     'descricao': 'Gibão de peles defensor. Se usar Ataque Poderoso ou fizer uma investida, recebe '
                  '+2d6 nas rolagens de dano.'},
    {'faixa': (21, 25), 'nome': 'Escudo do conjurador', 'preco': 'T$ 45.000', 'escudo': True,
     'descricao': 'Escudo leve defensor. Um conjurador pode armazenar uma magia na tira interna, '
                  'que depois é lida como um pergaminho.'},
    {'faixa': (26, 32), 'nome': 'Loriga do centurião', 'preco': 'T$ 45.000', 'escudo': False,
     'descricao': 'Loriga segmentada defensora. Se estiver liderando criaturas (usando Comandar ou '
                  'similar), seus ataques corpo a corpo causam +2d6 de fogo.'},
    {'faixa': (33, 42), 'nome': 'Manto da noite', 'preco': 'T$ 45.000', 'escudo': False,
     'descricao': 'Couro batido ajustado defensor sombrio. Sem penalidade de Furtividade por se mover '
                  'no deslocamento normal; a penalidade por atacar diminui para –10.'},
    {'faixa': (43, 49), 'nome': 'Couraça do comando', 'preco': 'T$ 45.000', 'escudo': False,
     'descricao': 'Couraça banhada a ouro sob medida defensora. +1 em Carisma; com o poder Comandar, '
                  'o bônus fornecido aumenta para +2.'},
    {'faixa': (50, 59), 'nome': 'Baluarte anão', 'preco': 'T$ 50.000', 'escudo': False,
     'descricao': 'Armadura completa reforçada defensora de adamante. Se você não se deslocar em seu '
                  'turno, a RD que ela fornece aumenta para 10 até seu próximo turno.'},
    {'faixa': (60, 66), 'nome': 'Escudo espinhoso', 'preco': 'T$ 50.000', 'escudo': True,
     'descricao': 'Escudo pesado defensor. Ação de movimento e 2 PM para disparar um espinho em '
                  'alcance curto: acerta automaticamente e causa 1d10+2 de perfuração.'},
    {'faixa': (67, 76), 'nome': 'Escudo do leão', 'preco': 'T$ 50.000', 'escudo': True,
     'descricao': 'Escudo pesado defensor. Uma vez por rodada, gaste 2 PM para a cabeça de leão '
                  'morder uma criatura adjacente: acerta automaticamente e causa 2d6+2 de perfuração.'},
    {'faixa': (77, 83), 'nome': 'Carapaça demoníaca', 'preco': 'T$ 63.000', 'escudo': False,
     'descricao': 'Armadura completa macabra reforçada guardiã. Se for devoto de uma divindade que '
                  'canaliza apenas energia negativa, seus ataques corpo a corpo causam +1d8 de trevas.'},
    {'faixa': (84, 88), 'nome': 'Escudo do eclipse', 'preco': 'T$ 70.000', 'escudo': True,
     'descricao': 'Escudo pesado defensor. Fornece redução de trevas 10 e causa +1d8 de dano de '
                  'trevas num ataque; ação de movimento e 2 PM para lançar Escuridão.'},
    {'faixa': (89, 93), 'nome': 'Escudo de Azgher', 'preco': 'T$ 140.000', 'escudo': True,
     'descricao': 'Escudo pesado guardião. Ação padrão e 10 PM: cone de alcance curto com efeito de '
                  'Visão da Verdade e 6d6 de dano de fogo (6d8 em mortos-vivos e criaturas '
                  'vulneráveis a luz solar).'},
    {'faixa': (94, 100), 'nome': 'Armadura da luz', 'preco': 'T$ 150.000', 'escudo': False,
     'descricao': 'Armadura completa banhada a ouro reforçada guardiã zelosa. Com código de conduta '
                  'ou devoção a divindade de energia positiva, recebe redução de dano igual ao '
                  'seu Carisma.'},
]

RARIDADES = {'menor': ('Menor', 1), 'medio': ('Médio', 2), 'maior': ('Maior', 3)}

# ---------------------------------------------------------------------------
# Rolagem de dados
# ---------------------------------------------------------------------------

MAX_DADOS = 100
MAX_FACES = 1000
MAX_EXPRESSOES = 10

MAX_CANDIDATOS = 100

DICE_RE = re.compile(r"^(?P<count>\d*)d(?P<sides>\d+)$")
TOKEN_RE = re.compile(r'([+-]?)(\d*d\d+|\d+)')

# Captura a expressão inteira dentro do texto da mensagem, tolerando espaços em
# volta dos sinais: "1d20+5", "1d20 + 5" e "1d20+ 5" são a mesma coisa.
# Os lookarounds evitam pegar pedaços de palavras como "abc1d6" ou "1d6x".
TERMO = r'(?:\d*[dD]\d+|\d+)'
EXPR_RE = re.compile(rf'(?<!\w){TERMO}(?:\s*[+-]\s*{TERMO})*(?!\w)')


def evaluate_complex(expr: str):
    """Avalia expressões compostas como '2d6+1d4+5' ou '1d12-2'.

    Espaços são ignorados e 'D' maiúsculo é aceito. Retorna None se não for uma
    expressão de dados válida, ou um dicionário com a chave 'error' se for uma
    expressão de dados fora dos limites aceitos.
    """
    s = re.sub(r'\s+', '', expr).lower()
    if not s:
        return None
    pos = 0
    components = []
    total = 0
    for m in TOKEN_RE.finditer(s):
        if m.start() != pos:
            return None
        pos = m.end()
        sign = -1 if m.group(1) == '-' else 1
        token = m.group(2)
        if 'd' in token:
            dm = DICE_RE.match(token)
            if not dm:
                return None
            count = int(dm.group('count') or '1')
            sides = int(dm.group('sides'))
            if sides < 1:
                return {'expr': expr, 'error': f'`{token}`: um dado precisa ter pelo menos 1 face.'}
            if sides > MAX_FACES:
                return {'expr': expr, 'error': f'`{token}`: no máximo {MAX_FACES} faces por dado.'}
            if count > MAX_DADOS:
                return {'expr': expr, 'error': f'`{token}`: no máximo {MAX_DADOS} dados por rolagem.'}
            rolls = [random.randint(1, sides) for _ in range(count)]
            value = sum(rolls)
            components.append({'type': 'dice', 'token': token, 'rolls': rolls, 'value': value,
                               'sign': sign})
            total += sign * value
        else:
            val = int(token)
            components.append({'type': 'const', 'token': token, 'value': val, 'sign': sign})
            total += sign * val
    if pos != len(s):
        return None
    # "5" ou "10+2" não são rolagens; exige ao menos um dado.
    if not any(c['type'] == 'dice' for c in components):
        return None
    return {"expr": expr, "components": components, "total": total}


def roll_message(texto: str):
    """Extrai e resolve todas as rolagens de uma mensagem.

    Retorna (resultados, erros). Uma mensagem sem nenhuma expressão de dados
    devolve duas listas vazias, e o bot fica calado.
    """
    resultados = []
    erros = []
    for i, m in enumerate(EXPR_RE.finditer(texto)):
        if i >= MAX_CANDIDATOS or len(resultados) + len(erros) >= MAX_EXPRESSOES:
            break
        r = evaluate_complex(m.group(0))
        if not r:
            continue
        if r.get('error'):
            erros.append(r['error'])
        else:
            resultados.append(r)
    return resultados, erros


# ---------------------------------------------------------------------------
# Estado da campanha (por servidor)
# ---------------------------------------------------------------------------

data = {"guilds": {}}



TERRENO_DIFICIL_PADRAO = {'florestas', 'pantanos', 'montanhas', 'artico'}
CLIMA_BOM = {'ensolarado'}


def compute_travel_distance(deslocamento_m: float, tempo_horas: int, terrain: str = None,
                            climate: str = None, marcha_forcada: bool = False,
                            terreno_dificil: bool = None, clima_ruim: bool = None) -> float:
    """Retorna a distância percorrida em km, conforme a Tabela 6-4 (p.270)."""
    desloc = float(deslocamento_m) if deslocamento_m else 6.0
    km = desloc * 0.5 * tempo_horas
    if terreno_dificil is None:
        terreno_dificil = terrain in TERRENO_DIFICIL_PADRAO
    if clima_ruim is None:
        clima_ruim = climate is not None and climate not in CLIMA_BOM
    if terreno_dificil:
        km *= 0.5
    if clima_ruim:
        km *= 0.5
    if marcha_forcada:
        km *= 2
    return km



# ---------------------------------------------------------------------------
# Recompensas: armaduras e escudos mágicos (p.338)
# ---------------------------------------------------------------------------


def _rolar_tabela(tabela, filtro=None):
    """Rola 1d% na tabela, repetindo enquanto o resultado não passar no filtro.

    Repetir a rolagem preserva os pesos relativos das faixas d%.
    """
    for _ in range(500):
        r = random.randint(1, 100)
        for linha in tabela:
            lo, hi = linha['faixa']
            if lo <= r <= hi:
                if filtro is None or filtro(linha):
                    return r, linha
                break
    return None, None


def generate_magic_armor(raridade: str = 'medio', tipo: str = None, evitar_repetidos: bool = True):
    """Gera uma armadura ou escudo mágico conforme a p.338.

    - `raridade`: 'menor', 'medio' ou 'maior'. No livro isso vem da tabela de tesouro
      do encontro (p.330), por isso é parâmetro e não sorteio.
    - `tipo`: None (rola na Tabela 8-4), 'armadura' ou 'escudo' para restringir.
    - `evitar_repetidos`: única casa de regra deste gerador. O livro não trata encantos
      duplicados; repetir o mesmo encanto não teria efeito mecânico, então rolamos de novo.
    """
    if raridade not in RARIDADES:
        raise ValueError(f"raridade inválida: {raridade!r}")
    nome_raridade, n_encantos = RARIDADES[raridade]

    filtro_tipo = None
    if tipo == 'escudo':
        filtro_tipo = lambda linha: linha['escudo']       # noqa: E731
    elif tipo == 'armadura':
        filtro_tipo = lambda linha: not linha['escudo']   # noqa: E731

    rolagens = []
    r_base, base = _rolar_tabela(TABELA_8_4_ARMADURAS, filtro_tipo)
    rolagens.append(f"Tabela 8-4: {r_base} → {base['nome']}")

    encantos = []
    notas = []
    restantes = n_encantos

    while restantes > 0:
        def valido(linha, _restantes=restantes):
            # Nota 1: Animado e Esmagador são apenas para escudos.
            if linha.get('apenas_escudo') and not base['escudo']:
                return False
            # Nota 2: Guardião vale dois encantos; em itens menores, role novamente.
            if linha.get('vale_dois') and _restantes < 2:
                return False
            if evitar_repetidos and any(e['nome'] == linha['nome'] for e in encantos):
                return False
            return True

        r, encanto = _rolar_tabela(TABELA_8_10_ENCANTOS, valido)
        if encanto is None:
            break
        rolagens.append(f"Tabela 8-10: {r} → {encanto['nome']}")

        if encanto.get('especifico'):
            # O item perde quaisquer encantos rolados e vira um item específico.
            r_esp, especifico = _rolar_tabela(TABELA_8_11_ESPECIFICOS, filtro_tipo)
            rolagens.append(f"Tabela 8-11: {r_esp} → {especifico['nome']}")
            return {
                'item': especifico['nome'],
                'is_shield': especifico['escudo'],
                'rarity': nome_raridade,
                'enchants': [],
                'specific': especifico,
                'notes': ['Resultado "item específico" na Tabela 8-10: o item perde quaisquer '
                          'encantos rolados (p.338).'],
                'rolls': rolagens,
            }

        encantos.append(encanto)
        if encanto.get('vale_dois'):
            restantes -= 2
            notas.append(f"{encanto['nome']} conta como dois encantos.")
        else:
            restantes -= 1

    if any(e['nome'] == 'Guardião' for e in encantos):
        notas.append('Guardião tem *defensor* como pré-requisito.')

    return {
        'item': base['nome'],
        'is_shield': base['escudo'],
        'rarity': nome_raridade,
        'enchants': encantos,
        'specific': None,
        'notes': notas,
        'rolls': rolagens,
    }

