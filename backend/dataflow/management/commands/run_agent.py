"""
Executa o agente diretamente via CLI para testes rápidos.

Usage:
    python manage.py run_agent --file path/to/data.csv
    python manage.py run_agent --sample
    echo "col1,col2\\n1,2" | python manage.py run_agent --stdin
"""
import sys

from django.core.management.base import BaseCommand

from dataflow.agent import DataFlowAgent


SAMPLE_DATA = """nome,email,idade,cidade,salario,departamento
Ana Silva,ana@email.com,28,São Paulo,5500.00,Engenharia
Bruno Costa,bruno@email.com,35,Rio de Janeiro,7200.00,Produto
Carla Dias,,42,Belo Horizonte,8100.00,Engenharia
Diego Ferreira,diego@email.com,31,,6300.00,Marketing
Eva Gomes,eva@email.com,26,São Paulo,4800.00,Design
Felipe Henrique,felipe@email.com,38,Curitiba,9200.00,Engenharia
Gabriela Lima,gabriela@email.com,29,São Paulo,,Produto
Hugo Martins,hugo@email.com,33,Rio de Janeiro,6800.00,Marketing
Isabela Nunes,isabela@email.com,27,Belo Horizonte,5100.00,Design
João Oliveira,joao@email.com,45,São Paulo,12000.00,Engenharia
Ana Silva,ana@email.com,28,São Paulo,5500.00,Engenharia
Karen Pereira,,31,Curitiba,6600.00,Produto
Lucas Queiroz,lucas@email.com,36,Rio de Janeiro,7800.00,Marketing
Mariana Reis,mariana@email.com,24,São Paulo,4200.00,Design
Nicolas Santos,nicolas@email.com,41,,10500.00,Engenharia
"""


class Command(BaseCommand):
    help = "Executa o agente de processamento de dados via CLI."

    def add_arguments(self, parser):
        parser.add_argument("--file", type=str, help="Caminho para arquivo CSV/JSON.")
        parser.add_argument("--sample", action="store_true", help="Usa dados de exemplo.")
        parser.add_argument("--stdin", action="store_true", help="Lê dados do stdin.")
        parser.add_argument("--context", type=str, default="", help="Contexto adicional.")

    def handle(self, *args, **options):
        # Determina a fonte dos dados
        if options["sample"]:
            data = SAMPLE_DATA
            self.stdout.write("Usando dados de exemplo (15 funcionários com problemas)...\n")
        elif options["file"]:
            with open(options["file"], "r", encoding="utf-8") as f:
                data = f.read()
            self.stdout.write(f"Lendo arquivo: {options['file']}\n")
        elif options["stdin"]:
            data = sys.stdin.read()
            self.stdout.write("Lendo dados do stdin...\n")
        else:
            self.stdout.write(self.style.WARNING(
                "Use --sample, --file ou --stdin. Usando --sample como padrão.\n"
            ))
            data = SAMPLE_DATA

        # Executa o agente
        self.stdout.write(self.style.HTTP_INFO("=" * 60))
        self.stdout.write(self.style.HTTP_INFO(" DataFlow Agent — Processamento"))
        self.stdout.write(self.style.HTTP_INFO("=" * 60))
        self.stdout.write("")

        agent = DataFlowAgent()
        result = agent.process(sample_data=data, context=options["context"])

        # Exibe resultado
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("=" * 60))
        self.stdout.write(self.style.HTTP_INFO(" Resultado"))
        self.stdout.write(self.style.HTTP_INFO("=" * 60))
        self.stdout.write("")

        for i, decision in enumerate(result["decisions"], 1):
            step = decision["step"].upper()
            reasoning = decision["reasoning"][:200]
            tokens = decision["tokens_used"]
            latency = decision["latency_ms"]

            self.stdout.write(
                self.style.SUCCESS(f"[{step}]") + f" ({tokens} tokens, {latency}ms)"
            )
            self.stdout.write(f"  {reasoning}")
            self.stdout.write("")

        self.stdout.write(self.style.HTTP_INFO("-" * 60))
        self.stdout.write(f"  Iterações:     {result['iterations']}")
        self.stdout.write(f"  Total tokens:  {result['total_tokens']}")
        self.stdout.write(f"  Quality score: {result['quality_score']}")
        self.stdout.write(self.style.HTTP_INFO("-" * 60))
