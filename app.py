import os
import sqlite3
import re
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, jsonify
import yfinance as yf

app = Flask(__name__)
DATABASE = 'cortex_invest.db'

CAPITAL_TOTAL_FIXO = 4000.00

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS operacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_insercao TEXT,
            ativo TEXT,
            strike REAL,
            premio REAL,
            tipo TEXT,
            vencimento TEXT,
            custos REAL,
            irrf REAL,
            premio_liquido REAL,
            estrategia TEXT,
            status TEXT,
            contratos INTEGER,
            nota INTEGER,
            alerta TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def buscar_cotacao_acao_mae(codigo_ativo):
    """
    Extrai as 4 letras iniciais do ticker de opção (ex: CPLES15 -> CPLE) 
    e descobre a cotação da ação mãe mais comum (geralmente ordinária ou preferencial)
    """
    # Pega apenas as letras iniciais do código digitado
    letras = re.sub(r'[^a-zA-Z]', '', codigo_ativo).upper()
    
    if len(letras) == 4:
        # Padrões comuns da B3 (BBDC4, CPLE6, PETR4, ITSA4)
        mapeamento_comum = {
            "CPLE": "CPLE6",
            "BBDC": "BBDC4",
            "ITSA": "ITSA4",
            "GOAU": "GOAU4",
            "PETR": "PETR4",
            "VALE": "VALE3"
        }
        ticker_mae = mapeamento_comum.get(letras, f"{letras}4")
    else:
        ticker_mae = codigo_ativo.upper()

    if not ticker_mae.endswith('.SA'):
        ticker_nome = f"{ticker_mae}.SA"
    else:
        ticker_nome = ticker_mae

    try:
        ticker = yf.Ticker(ticker_nome)
        todays_data = ticker.history(period='1d')
        if not todays_data.empty:
            return round(todays_data['Close'].iloc[-1], 2)
        return 0.0
    except:
        return 0.0

@app.route('/')
def index():
    conn = get_db_connection()
    operacoes_rows = conn.execute('SELECT * FROM operacoes ORDER BY id DESC').fetchall()
    conn.close()

    operacoes = []
    capital_comprometido = 0.0
    total_premios_ativos = 0.0
    total_lucro_mes = 0.0
    
    qtd_abertas = 0
    qtd_encerradas = 0
    hoje = datetime.now().date()

    for row in operacoes_rows:
        op = dict(row)
        
        # Puxa dinamicamente a cotação da ação mãe
        op['cotacao_atual'] = buscar_cotacao_acao_mae(op['ativo'])
        
        try:
            venc_dt = datetime.strptime(op['vencimento'], '%Y-%m-%d').date()
            op['dias_restantes'] = (venc_dt - hoje).days
            if op['dias_restantes'] < 0:
                op['dias_restantes'] = 0
        except:
            op['dias_restantes'] = 0

        multiplicador_lote = op['contratos'] * 100
        valor_nocional = op['strike'] * multiplicador_lote
        
        if op['status'] == 'Aberta':
            qtd_abertas += 1
            total_premios_ativos += op['premio_liquido']
            if op['tipo'].upper() == 'PUT':
                capital_comprometido += valor_nocional
            else:
                capital_comprometido += (op['cotacao_atual'] if op['cotacao_atual'] > 0 else op['strike']) * multiplicador_lote
        else:
            qtd_encerradas += 1
            total_lucro_mes += op['premio_liquido']

        operacoes.append(op)

    # Corrigindo cálculos solicitados para a v2.1
    darf_mes = round(total_lucro_mes * 0.15, 2) if total_lucro_mes > 0 else 0.0
    pct_capital_comprometido = round((capital_comprometido / CAPITAL_TOTAL_FIXO) * 100, 2) if CAPITAL_TOTAL_FIXO > 0 else 0.0
    roi_mes = round((total_lucro_mes / CAPITAL_TOTAL_FIXO) * 100, 2) if CAPITAL_TOTAL_FIXO > 0 else 0.0
    
    # Recálculo exato do ROI das Abertas sobre o Capital que está real comprometido
    roi_abertas = round((total_premios_ativos / capital_comprometido) * 100, 2) if capital_comprometido > 0 else 0.0

    return render_template('index.html', 
                           operacoes=operacoes, 
                           capital_total=CAPITAL_TOTAL_FIXO,
                           capital_comprometido=capital_comprometido,
                           pct_comprometido=pct_capital_comprometido,
                           total_premios_ativos=total_premios_ativos,
                           total_lucro_mes=total_lucro_mes,
                           darf_mes=darf_mes,
                           roi_mes=roi_mes,
                           roi_abertas=roi_abertas,
                           qtd_abertas=qtd_abertas,
                           qtd_encerradas=qtd_encerradas,
                           total_operacoes=len(operacoes))

@app.route('/nova_operacao', methods=['POST'])
def nova_operacao():
    ativo = request.form['ativo'].upper()
    strike = float(request.form['strike'])
    premio = float(request.form['premio'])
    tipo = request.form['tipo']
    vencimento = request.form['vencimento']
    custos = float(request.form['custos'] or 0)
    contratos = int(request.form['contratos'] or 1)
    estrategia = request.form['estrategia']
    status = request.form['status']
    nota = int(request.form['nota'] or 0)
    alerta = request.form['alerta']
    
    data_insercao = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    premio_bruto_total = premio * contratos * 100
    irrf = round(premio_bruto_total * 0.00005, 2)
    premio_liquido = round(premio_bruto_total - custos - irrf, 2)

    conn = get_db_connection()
    conn.execute('''
        INSERT INTO operacoes (data_insercao, ativo, strike, premio, tipo, vencimento, custos, irrf, premio_liquido, estrategia, status, contratos, nota, alerta)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (data_insercao, ativo, strike, premio, tipo, vencimento, custos, irrf, premio_liquido, estrategia, status, contratos, nota, alerta))
    conn.commit()
    conn.close()
    
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
