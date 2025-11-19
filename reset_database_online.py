#!/usr/bin/env python3
"""
Script para resetar o banco de dados PostgreSQL online (Railway)
ATENÇÃO: Este script irá APAGAR TODOS OS DADOS do banco online!
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv
import sys
from datetime import datetime
import subprocess

# Carregar variáveis de ambiente (se houver .env)
load_dotenv()

class DatabaseReset:
    def __init__(self):
        # Preferir URL pública quando disponível (ambiente local)
        public_url = os.getenv('DATABASE_PUBLIC_URL')
        internal_url = os.getenv('DATABASE_URL')

        self.database_url = public_url or internal_url
        if not self.database_url:
            raise ValueError(
                "Nenhuma variável de conexão encontrada. Defina DATABASE_PUBLIC_URL ou DATABASE_URL."
            )

        # Converter para formato aceito pelo asyncpg se necessário
        if self.database_url.startswith('postgresql+asyncpg://'):
            self.database_url = self.database_url.replace('postgresql+asyncpg://', 'postgresql://')
        if self.database_url.startswith('postgresql+psycopg2://'):
            self.database_url = self.database_url.replace('postgresql+psycopg2://', 'postgresql://')
    
    async def connect(self, retries: int = 3, base_delay: float = 1.5):
        """Conectar ao banco PostgreSQL com retry e timeout."""
        last_err = None
        for attempt in range(1, retries + 1):
            try:
                # timeout geral de conexão (segundos)
                self.conn = await asyncpg.connect(self.database_url, timeout=10)
                print("✅ Conectado ao banco PostgreSQL online")
                return True
            except Exception as e:
                last_err = e
                msg = str(e)
                print(f"❌ Erro ao conectar (tentativa {attempt}/{retries}): {msg}")
                
                # Dicas específicas para erros comuns em Windows/rede
                if "WinError 64" in msg:
                    print("   💡 Dica: 'O nome de rede especificado já não está disponível' indica instabilidade de rede/VPN/Firewall.")
                    print("   - Verifique sua conexão, VPN/Proxy e tente novamente.")
                if "TLS handshake timeout" in msg or "handshake" in msg:
                    print("   💡 Dica: Timeout de TLS. Rede lenta/instável ou bloqueio de firewall.")
                    print("   - Tente novamente, verifique internet/antivírus/firewall.")

                if attempt < retries:
                    delay = base_delay * attempt
                    print(f"   ⏳ Aguardando {delay:.1f}s para nova tentativa...")
                    await asyncio.sleep(delay)
        print("❌ Falha ao conectar após múltiplas tentativas.")
        return False
    
    async def close(self):
        """Fechar conexão"""
        if hasattr(self, 'conn'):
            await self.conn.close()
            print("🔌 Conexão fechada")
    
    async def backup_data(self):
        """Fazer backup dos dados antes do reset"""
        print("📦 Fazendo backup dos dados...")
        backup_data = {}
        
        try:
            # Backup de usuários
            users = await self.conn.fetch("SELECT * FROM usuarios")
            backup_data['usuarios'] = [dict(row) for row in users]
            print(f"   - {len(users)} usuários salvos")
            
            # Backup de produtos
            produtos = await self.conn.fetch("SELECT * FROM produtos")
            backup_data['produtos'] = [dict(row) for row in produtos]
            print(f"   - {len(produtos)} produtos salvos")
            
            # Backup de clientes
            clientes = await self.conn.fetch("SELECT * FROM clientes")
            backup_data['clientes'] = [dict(row) for row in clientes]
            print(f"   - {len(clientes)} clientes salvos")
            
            # Backup de vendas
            vendas = await self.conn.fetch("SELECT * FROM vendas")
            backup_data['vendas'] = [dict(row) for row in vendas]
            print(f"   - {len(vendas)} vendas salvas")
            
            return backup_data
            
        except Exception as e:
            print(f"⚠️  Erro no backup: {e}")
            return {}
    
    async def drop_all_tables(self):
        """Remover todas as tabelas"""
        print("🗑️  Removendo todas as tabelas...")
        
        try:
            # Lista de tabelas para remover (ordem importa devido às foreign keys)
            tables_to_drop = [
                'itens_venda',
                'vendas', 
                'produtos',
                'clientes',
                'usuarios',  # nome real da tabela no schema
                'users'      # legado (caso exista em deploys antigos)
            ]
            
            for table in tables_to_drop:
                try:
                    await self.conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
                    print(f"   - Tabela {table} removida")
                except Exception as e:
                    print(f"   - Erro ao remover {table}: {e}")
            
            print("✅ Todas as tabelas removidas")
            
        except Exception as e:
            print(f"❌ Erro ao remover tabelas: {e}")
            raise
    
    async def create_tables(self):
        """Recriar todas as tabelas"""
        print("🏗️  Recriando tabelas...")
        
        try:
            # Garantir extensão para geração de UUIDs
            try:
                await self.conn.execute("""CREATE EXTENSION IF NOT EXISTS "pgcrypto";""")
            except Exception as ext_err:
                print(f"⚠️  Não foi possível garantir extensão pgcrypto automaticamente: {ext_err}")
                print("    Caso o banco não possua suporte a gen_random_uuid(), habilite manualmente.")
            
            # Tabela usuarios
            await self.conn.execute("""
                CREATE TABLE usuarios (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    nome VARCHAR(255) NOT NULL,
                    usuario VARCHAR(100) UNIQUE NOT NULL,
                    senha_hash VARCHAR(255) NOT NULL,
                    is_admin BOOLEAN DEFAULT FALSE,
                    ativo BOOLEAN DEFAULT TRUE,
                    nivel INTEGER DEFAULT 1,
                    salario NUMERIC(12,2) DEFAULT 0,
                    pode_abastecer BOOLEAN DEFAULT FALSE,
                    pode_gerenciar_despesas BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)
            print("   - Tabela usuarios criada")
            
            # Tabela produtos
            await self.conn.execute("""
                CREATE TABLE produtos (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    codigo VARCHAR(50) UNIQUE NOT NULL,
                    nome VARCHAR(255) NOT NULL,
                    descricao TEXT,
                    preco_custo NUMERIC(12,2) NOT NULL DEFAULT 0,
                    preco_venda NUMERIC(12,2) NOT NULL DEFAULT 0,
                    estoque NUMERIC(12,3) NOT NULL DEFAULT 0,
                    estoque_minimo NUMERIC(12,3) NOT NULL DEFAULT 0,
                    categoria_id INTEGER,
                    venda_por_peso BOOLEAN DEFAULT FALSE,
                    unidade_medida VARCHAR(10) DEFAULT 'un',
                    ativo BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)
            print("   - Tabela produtos criada")
            
            # Tabela clientes
            await self.conn.execute("""
                CREATE TABLE clientes (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    nome VARCHAR(255) NOT NULL,
                    documento VARCHAR(50),
                    telefone VARCHAR(50),
                    email VARCHAR(255),
                    endereco TEXT,
                    especial BOOLEAN DEFAULT FALSE,
                    desconto_divida NUMERIC(12,2) DEFAULT 0,
                    ativo BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)
            print("   - Tabela clientes criada")
            
            # Tabela vendas
            await self.conn.execute("""
                CREATE TABLE vendas (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    usuario_id UUID REFERENCES usuarios(id),
                    cliente_id UUID REFERENCES clientes(id),
                    total NUMERIC(12,2) NOT NULL,
                    desconto NUMERIC(12,2) DEFAULT 0,
                    forma_pagamento VARCHAR(50) NOT NULL,
                    valor_recebido NUMERIC(12,2),
                    troco NUMERIC(12,2),
                    data_venda TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    status VARCHAR(20) DEFAULT 'Ativa',
                    motivo_alteracao TEXT,
                    alterado_por UUID REFERENCES usuarios(id),
                    data_alteracao TIMESTAMPTZ,
                    origem VARCHAR(50) DEFAULT 'venda_direta',
                    valor_original_divida NUMERIC(12,2) DEFAULT 0,
                    desconto_aplicado_divida NUMERIC(12,2) DEFAULT 0,
                    observacoes TEXT,
                    cancelada BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)
            print("   - Tabela vendas criada")
            
            # Tabela itens_venda
            await self.conn.execute("""
                CREATE TABLE itens_venda (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    venda_id UUID NOT NULL REFERENCES vendas(id) ON DELETE CASCADE,
                    produto_id UUID NOT NULL REFERENCES produtos(id),
                    quantidade NUMERIC(12,3) NOT NULL,
                    peso_kg NUMERIC(12,3) DEFAULT 0,
                    preco_unitario NUMERIC(12,2) NOT NULL,
                    preco_custo_unitario NUMERIC(12,2) DEFAULT 0,
                    subtotal NUMERIC(12,2) NOT NULL,
                    status VARCHAR(20),
                    motivo_alteracao TEXT,
                    alterado_por UUID REFERENCES usuarios(id),
                    data_alteracao TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)
            print("   - Tabela itens_venda criada")
            
            print("✅ Todas as tabelas recriadas")
            
        except Exception as e:
            print(f"❌ Erro ao criar tabelas: {e}")
            raise
    
    async def create_admin_user(self):
        """Criar usuário admin padrão"""
        print("👤 Criando usuário admin padrão...")
        
        try:
            # Hash da senha '842384' (você deve usar bcrypt em produção)
            from passlib.context import CryptContext
            pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
            senha_hash = pwd_context.hash("842384")
            
            import uuid
            admin_uuid = uuid.uuid4()
            
            await self.conn.execute("""
                INSERT INTO usuarios (id, nome, usuario, senha_hash, is_admin, ativo)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, admin_uuid, "Hélder Alves", "Alves", senha_hash, True, True)
            
            print("✅ Usuário admin criado (nome: Hélder Alves, login: Alves, senha: 842384)")
            
        except Exception as e:
            print(f"❌ Erro ao criar usuário admin: {e}")
    
    async def reset_complete(self):
        """Reset completo do banco de dados"""
        print("🚨 INICIANDO RESET COMPLETO DO BANCO DE DADOS ONLINE")
        print("=" * 60)
        
        try:
            # 1. Fazer backup
            backup_data = await self.backup_data()
            
            # 2. Remover tabelas
            await self.drop_all_tables()
            
            # 3. Recriar tabelas
            await self.create_tables()
            
            # 4. (Opcional) Criar usuário admin - DESATIVADO por padrão para não atrapalhar a sincronização inicial
            # await self.create_admin_user()
            
            print("=" * 60)
            print("✅ RESET COMPLETO CONCLUÍDO COM SUCESSO!")
            print("📊 Resumo:")
            print(f"   - Backup realizado: {len(backup_data)} tabelas")
            print("   - Todas as tabelas recriadas")
            print("   - Usuário admin NÃO foi criado automaticamente (intencional)")
            
        except Exception as e:
            print(f"❌ ERRO NO RESET: {e}")
            raise
    
    async def reset_data_only(self):
        """Reset apenas dos dados (manter estrutura)"""
        print("🧹 INICIANDO LIMPEZA DOS DADOS (manter estrutura)")
        print("=" * 60)
        
        try:
            # Fazer backup
            backup_data = await self.backup_data()
            
            # Limpar dados das tabelas (ordem importa)
            tables_to_clear = ['itens_venda', 'vendas', 'produtos', 'clientes', 'usuarios']
            
            for table in tables_to_clear:
                try:
                    result = await self.conn.execute(f"DELETE FROM {table}")
                    print(f"   - Dados da tabela {table} removidos")
                except Exception as e:
                    print(f"   - Erro ao limpar {table}: {e}")
            
            # (Opcional) Criar usuário admin - DESATIVADO por padrão para não atrapalhar a sincronização inicial
            # await self.create_admin_user()
            
            print("=" * 60)
            print("✅ LIMPEZA DE DADOS CONCLUÍDA!")
            print("   - Estrutura das tabelas mantida")
            print("   - Todos os dados removidos")
            print("   - Usuário admin NÃO foi recriado automaticamente (intencional)")
            
        except Exception as e:
            print(f"❌ ERRO NA LIMPEZA: {e}")
            raise

def confirm_action(action_name):
    """Confirmar ação perigosa"""
    print(f"\n⚠️  ATENÇÃO: Você está prestes a {action_name}")
    print("🚨 ESTA AÇÃO IRÁ APAGAR DADOS DO BANCO ONLINE!")
    print("📍 Banco: Railway PostgreSQL")
    
    confirm1 = input("\nDigite 'CONFIRMO' para continuar: ").strip()
    if confirm1 != 'CONFIRMO':
        print("❌ Operação cancelada")
        return False
    
    confirm2 = input("Digite 'SIM' para confirmar novamente: ").strip()
    if confirm2 != 'SIM':
        print("❌ Operação cancelada")
        return False
    
    print("✅ Confirmação recebida. Iniciando operação...")
    return True

async def main():
    """Função principal"""
    print("🗄️  SCRIPT DE RESET DO BANCO POSTGRESQL ONLINE")
    print("=" * 60)
    
    if len(sys.argv) < 2:
        print("Uso:")
        print("  python reset_database_online.py complete    # Reset completo")
        print("  python reset_database_online.py data        # Limpar apenas dados")
        print("  python reset_database_online.py check       # Verificar conexão")
        return
    
    action = sys.argv[1].lower()
    
    # Verificar se o arquivo .env existe
    # .env é opcional: podemos usar variáveis do ambiente do shell
    if not os.path.exists('.env'):
        print("⚠️  Arquivo .env não encontrado. Continuando com variáveis de ambiente do sistema (se definidas)...")
    
    reset_db = DatabaseReset()
    
    try:
        # Conectar ao banco
        if not await reset_db.connect():
            return
        
        if action == 'check':
            print("✅ Conexão com o banco online OK!")
            
        elif action == 'complete':
            if confirm_action("fazer RESET COMPLETO do banco"):
                await reset_db.reset_complete()
                
        elif action == 'data':
            if confirm_action("LIMPAR TODOS OS DADOS do banco"):
                await reset_db.reset_data_only()
                
        else:
            print(f"❌ Ação '{action}' não reconhecida")
            
    except Exception as e:
        print(f"❌ Erro geral: {e}")
        
    finally:
        await reset_db.close()

if __name__ == "__main__":
    # Instalar dependências necessárias
    try:
        import asyncpg
        import passlib
    except ImportError:
        print("❌ Dependências faltando. Execute:")
        print("   pip install asyncpg passlib[bcrypt]")
        sys.exit(1)
    
    asyncio.run(main())
