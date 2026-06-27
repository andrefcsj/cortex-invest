Python
import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, jsonify
import yfinance as yf

app = Flask(__name__)
DATABASE = 'cortex_invest.db'

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

# Inicializa o banco de dados na primeira execução
init_db()

def buscar_cotacao(ativo_nome):
    # Adiciona .SA se for ativo brasileiro e o usuário esquecer
    if not ativo_nome.endswith('.SA') and len(ativo_nome) <= 6:
        ticker_nome = f"{ativo_nome.upper()}.SA"
    else:
        ticker_nome = ativo_nome.upper()
    try:
        ticker = yf.Ticker(ticker_nome)
        # Tenta pegar o preço de fechamento mais recente
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
    darf_mes = 0.0

    hoje = datetime.now().date()

    for row in operacoes_rows:
        op = dict(row)
        
        # Buscar cotação atualizada na hora
        op['cotacao_atual'] = buscar_cotacao(op['ativo'])
        
        # Calcular dias restantes
        try:
            venc_dt = datetime.strptime(op['vencimento'], '%Y-%m-%d').date()
            op['dias_restantes'] = (venc_dt - hoje).days
            if op['dias_restantes'] < 0:
                op['dias_restantes'] = 0
        except:
            op['dias_restantes'] = 0

        # Regra de cálculos para Dashboard
        valor_operacao = op['strike'] * op['contratos'] * 100 # Lote padrão 100
        
        if op['status'] == 'Aberta':
            capital_comprometido += valor_operacao
            total_premios_ativos += op['premio_liquido']
        else:
            total_lucro_mes += op['premio_liquido']

        operacoes.append(op)

    # Cálculos de ROI
    roi_abertas = 0.0
    if capital_comprometido > 0:
        roi_abertas = round((total_premios_ativos / capital_comprometido) * 100, 2)

    return render_template('index.html', 
                           operacoes=operacoes, 
                           capital_comprometido=capital_comprometido,
                           total_premios_ativos=total_premios_ativos,
                           total_lucro_mes=total_lucro_mes,
                           roi_abertas=roi_abertas)

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

    # Cálculos automáticos solicitados
    premio_bruto_total = premio * contratos * 100
    # IRRF retido na fonte estimado para opções (0.005% das operações ou simplificado sobre lucro)
    irrf = round(premio_bruto_total * 0.0005, 2) 
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
