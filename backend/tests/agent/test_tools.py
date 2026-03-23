"""
Testes unitários para os tool handlers do DataFlow Agent.

Cada handler é testado de forma isolada, sem dependência da API Anthropic
ou do Django ORM.
"""
import pytest

from dataflow.agent.tools import (
    _SESSION_STORE,
    assess_quality,
    detect_schema,
    execute_transform,
    plan_transformation,
    validate_output,
)


# ──────────────────────────────────────────────
# detect_schema
# ──────────────────────────────────────────────

class TestDetectSchema:
    def test_retorna_session_id(self, csv_com_nulos):
        resultado = detect_schema(csv_com_nulos)
        assert "session_id" in resultado
        assert isinstance(resultado["session_id"], str)
        assert len(resultado["session_id"]) == 36  # UUID v4

    def test_armazena_dataframe_no_store(self, csv_com_nulos):
        resultado = detect_schema(csv_com_nulos)
        session_id = resultado["session_id"]
        assert session_id in _SESSION_STORE
        _SESSION_STORE.pop(session_id, None)  # limpeza

    def test_schema_colunas_corretas(self, csv_com_nulos):
        resultado = detect_schema(csv_com_nulos)
        nomes = [c["name"] for c in resultado["columns"]]
        assert set(nomes) == {"nome", "idade", "salario", "cidade"}
        _SESSION_STORE.pop(resultado["session_id"], None)

    def test_contagem_de_linhas(self, csv_com_nulos):
        resultado = detect_schema(csv_com_nulos)
        # CSV tem 6 linhas de dados (sem header)
        assert resultado["row_count"] == 6
        _SESSION_STORE.pop(resultado["session_id"], None)

    def test_detecta_nulos_na_coluna(self, csv_com_nulos):
        resultado = detect_schema(csv_com_nulos)
        col_idade = next(c for c in resultado["columns"] if c["name"] == "idade")
        assert col_idade["null_count"] == 1
        assert col_idade["null_pct"] > 0
        _SESSION_STORE.pop(resultado["session_id"], None)

    def test_formato_json(self, json_simples):
        resultado = detect_schema(json_simples)
        assert "error" not in resultado
        assert resultado["column_count"] == 2
        _SESSION_STORE.pop(resultado["session_id"], None)

    def test_formato_invalido(self):
        resultado = detect_schema("isso não é csv nem json {{{{")
        assert "error" in resultado


# ──────────────────────────────────────────────
# assess_quality
# ──────────────────────────────────────────────

class TestAssessQuality:
    def test_calcula_null_pct(self, csv_com_nulos):
        schema = detect_schema(csv_com_nulos)
        resultado = assess_quality(schema["session_id"])
        assert resultado["overall_null_pct"] > 0
        _SESSION_STORE.pop(schema["session_id"], None)

    def test_calcula_duplicatas(self, csv_com_nulos):
        schema = detect_schema(csv_com_nulos)
        resultado = assess_quality(schema["session_id"])
        # Alice linha 1 == Alice linha 6
        assert resultado["duplicate_count"] == 1
        assert resultado["duplicate_pct"] > 0
        _SESSION_STORE.pop(schema["session_id"], None)

    def test_sem_nulos_e_duplicatas_em_csv_limpo(self, csv_limpo):
        schema = detect_schema(csv_limpo)
        resultado = assess_quality(schema["session_id"])
        assert resultado["duplicate_count"] == 0
        assert resultado["overall_null_pct"] == 0.0
        # outliers estatísticos podem existir mesmo em dados "limpos" (IQR com poucos pontos)
        null_issues = [i for i in resultado["quality_issues"] if "nulo" in i]
        dup_issues = [i for i in resultado["quality_issues"] if "duplicada" in i]
        assert len(null_issues) == 0
        assert len(dup_issues) == 0
        _SESSION_STORE.pop(schema["session_id"], None)

    def test_lista_quality_issues(self, csv_com_nulos):
        schema = detect_schema(csv_com_nulos)
        resultado = assess_quality(schema["session_id"])
        assert isinstance(resultado["quality_issues"], list)
        assert len(resultado["quality_issues"]) > 0
        _SESSION_STORE.pop(schema["session_id"], None)

    def test_sessao_invalida(self):
        resultado = assess_quality("sessao-inexistente")
        assert "error" in resultado


# ──────────────────────────────────────────────
# execute_transform — drop_nulls
# ──────────────────────────────────────────────

class TestExecuteTransformDropNulls:
    def test_remove_linhas_com_nulos(self, csv_com_nulos):
        schema = detect_schema(csv_com_nulos)
        sid = schema["session_id"]
        resultado = execute_transform(sid, "drop_nulls", {})
        assert resultado["status"] == "success"
        assert resultado["rows_after"] < resultado["rows_before"]
        _SESSION_STORE.pop(sid, None)

    def test_remove_nulos_em_subset(self, csv_com_nulos):
        schema = detect_schema(csv_com_nulos)
        sid = schema["session_id"]
        rows_antes = schema["row_count"]
        resultado = execute_transform(sid, "drop_nulls", {"columns": ["idade"]})
        assert resultado["rows_after"] == rows_antes - 1  # apenas Bob sem idade
        _SESSION_STORE.pop(sid, None)

    def test_persiste_dataframe_modificado(self, csv_com_nulos):
        schema = detect_schema(csv_com_nulos)
        sid = schema["session_id"]
        execute_transform(sid, "drop_nulls", {})
        df = _SESSION_STORE[sid]
        assert df.isnull().sum().sum() == 0
        _SESSION_STORE.pop(sid, None)


# ──────────────────────────────────────────────
# execute_transform — rename_columns
# ──────────────────────────────────────────────

class TestExecuteTransformRename:
    def test_renomeia_coluna(self, csv_limpo):
        schema = detect_schema(csv_limpo)
        sid = schema["session_id"]
        resultado = execute_transform(sid, "rename_columns", {"mapping": {"nome": "name"}})
        assert resultado["status"] == "success"
        assert "name" in resultado["columns"]
        assert "nome" not in resultado["columns"]
        _SESSION_STORE.pop(sid, None)


# ──────────────────────────────────────────────
# execute_transform — deduplicate
# ──────────────────────────────────────────────

class TestExecuteTransformDedup:
    def test_remove_duplicatas(self, csv_com_nulos):
        schema = detect_schema(csv_com_nulos)
        sid = schema["session_id"]
        rows_antes = schema["row_count"]
        resultado = execute_transform(sid, "deduplicate", {})
        assert resultado["rows_after"] < rows_antes
        assert resultado["rows_affected"] >= 1
        _SESSION_STORE.pop(sid, None)


# ──────────────────────────────────────────────
# execute_transform — cast_types
# ──────────────────────────────────────────────

class TestExecuteTransformCast:
    def test_converte_tipo(self, csv_limpo):
        schema = detect_schema(csv_limpo)
        sid = schema["session_id"]
        resultado = execute_transform(sid, "cast_types", {"column": "salario", "dtype": "int"})
        assert resultado["status"] == "success"
        import pandas as pd
        assert pd.api.types.is_integer_dtype(_SESSION_STORE[sid]["salario"])
        _SESSION_STORE.pop(sid, None)

    def test_coluna_inexistente(self, csv_limpo):
        schema = detect_schema(csv_limpo)
        sid = schema["session_id"]
        resultado = execute_transform(sid, "cast_types", {"column": "inexistente", "dtype": "int"})
        assert "error" in resultado
        _SESSION_STORE.pop(sid, None)


# ──────────────────────────────────────────────
# execute_transform — fill_nulls
# ──────────────────────────────────────────────

class TestExecuteTransformFillNulls:
    def test_preenche_nulos_em_coluna(self, csv_com_nulos):
        schema = detect_schema(csv_com_nulos)
        sid = schema["session_id"]
        execute_transform(sid, "fill_nulls", {"column": "idade", "value": 0})
        df = _SESSION_STORE[sid]
        assert df["idade"].isnull().sum() == 0
        _SESSION_STORE.pop(sid, None)


# ──────────────────────────────────────────────
# execute_transform — normalize
# ──────────────────────────────────────────────

class TestExecuteTransformNormalize:
    def test_normaliza_entre_0_e_1(self, csv_limpo):
        schema = detect_schema(csv_limpo)
        sid = schema["session_id"]
        execute_transform(sid, "normalize", {"columns": ["salario"]})
        df = _SESSION_STORE[sid]
        assert df["salario"].min() >= 0.0
        assert df["salario"].max() <= 1.0
        _SESSION_STORE.pop(sid, None)


# ──────────────────────────────────────────────
# validate_output
# ──────────────────────────────────────────────

class TestValidateOutput:
    def test_score_100_para_dados_limpos(self, csv_limpo):
        schema = detect_schema(csv_limpo)
        sid = schema["session_id"]
        resultado = validate_output(sid)
        assert resultado["quality_score"] == 100.0
        assert resultado["null_pct"] == 0.0
        assert resultado["duplicate_pct"] == 0.0

    def test_score_reduzido_com_nulos(self, csv_com_nulos):
        schema = detect_schema(csv_com_nulos)
        sid = schema["session_id"]
        resultado = validate_output(sid)
        assert resultado["quality_score"] < 100.0

    def test_limpa_sessao_apos_validacao(self, csv_limpo):
        schema = detect_schema(csv_limpo)
        sid = schema["session_id"]
        validate_output(sid)
        assert sid not in _SESSION_STORE

    def test_detecta_schema_drift(self, csv_limpo):
        schema = detect_schema(csv_limpo)
        sid = schema["session_id"]
        expected = {"columns": [{"name": "coluna_inexistente"}]}
        resultado = validate_output(sid, expected_schema=expected)
        assert resultado["schema_drift_detected"] is True
        assert resultado["quality_score"] < 100.0

    def test_sessao_invalida(self):
        resultado = validate_output("sessao-inexistente")
        assert "error" in resultado


# ──────────────────────────────────────────────
# plan_transformation
# ──────────────────────────────────────────────

class TestPlanTransformation:
    def test_valida_steps_conhecidos(self, csv_limpo):
        schema = detect_schema(csv_limpo)
        sid = schema["session_id"]
        steps = [
            {"operation": "drop_nulls", "params": {}, "rationale": "remover nulos"},
            {"operation": "deduplicate", "params": {}, "rationale": "remover dups"},
        ]
        resultado = plan_transformation(sid, [], steps)
        assert resultado["status"] == "plan_validated"
        assert resultado["total_steps"] == 2
        _SESSION_STORE.pop(sid, None)

    def test_ignora_operacoes_invalidas(self, csv_limpo):
        schema = detect_schema(csv_limpo)
        sid = schema["session_id"]
        steps = [
            {"operation": "operacao_inventada", "params": {}},
            {"operation": "drop_nulls", "params": {}},
        ]
        resultado = plan_transformation(sid, [], steps)
        assert resultado["total_steps"] == 1
        assert len(resultado["warnings"]) == 1
        _SESSION_STORE.pop(sid, None)
