# -*- coding: utf-8 -*-
"""
TADM23 クイズアプリ
Streamlitベースの学習用クイズアプリケーション（スマホ最適化版）
Google Sheetsで永続化 + 選択肢ランダム化
"""

import streamlit as st
import json
import random
import hashlib
from datetime import datetime
from pathlib import Path
import pandas as pd
from streamlit_gsheets import GSheetsConnection

# ページ設定（スマホ向けにcenteredレイアウト）
st.set_page_config(
    page_title="TADM23 クイズ",
    page_icon="📚",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# スマホ向けカスタムCSS
st.markdown("""
<style>
    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
        padding-left: 0.5rem;
        padding-right: 0.5rem;
    }
    h1, h2, h3 {
        margin-top: 0.3rem;
        margin-bottom: 0.3rem;
    }
    .correct-answer {
        background-color: #d4edda;
        border: 2px solid #28a745;
        padding: 8px;
        border-radius: 8px;
        margin: 4px 0;
        color: #155724;
        font-size: 0.9em;
    }
    .incorrect-answer {
        background-color: #f8d7da;
        border: 2px solid #dc3545;
        padding: 8px;
        border-radius: 8px;
        margin: 4px 0;
        color: #721c24;
        font-size: 0.9em;
    }
    .question-box {
        background-color: #e8f4f8;
        padding: 12px;
        border-radius: 10px;
        margin-bottom: 10px;
        border: 2px solid #bee5eb;
        color: #0c5460;
        font-size: 0.95em;
        line-height: 1.5;
    }
    .explanation-box {
        background-color: #fff3cd;
        border: 2px solid #ffc107;
        padding: 10px;
        border-radius: 8px;
        margin-top: 10px;
        color: #856404;
        font-size: 0.85em;
        line-height: 1.5;
        white-space: pre-wrap;
    }
    .badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.75em;
        font-weight: bold;
    }
    .badge-count {
        background-color: #17a2b8;
        color: #fff;
    }
    .badge-stats {
        background-color: #6c757d;
        color: #fff;
    }
    .stButton > button {
        font-size: 1em;
        padding: 0.5rem 1rem;
        border-radius: 8px;
    }
    .stRadio > div, .stCheckbox > div {
        font-size: 0.9em;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 2px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 8px 12px;
        font-size: 0.85em;
    }
</style>
""", unsafe_allow_html=True)


# =============================================================================
# Google Sheets データベース関連
# =============================================================================

def get_user_id():
    """ユーザーIDを取得（ブラウザセッションごとにユニーク）"""
    if "user_id" not in st.session_state:
        # クエリパラメータからユーザーIDを取得、なければ新規生成
        params = st.query_params
        if "uid" in params:
            st.session_state.user_id = params["uid"]
        else:
            # 新しいユーザーIDを生成
            new_id = hashlib.md5(f"{datetime.now().isoformat()}{random.random()}".encode()).hexdigest()[:12]
            st.session_state.user_id = new_id
            st.query_params["uid"] = new_id
    return st.session_state.user_id


@st.cache_resource
def get_gsheets_connection():
    """Google Sheets接続を取得"""
    try:
        return st.connection("gsheets", type=GSheetsConnection)
    except Exception as e:
        st.error(f"Google Sheets接続エラー: {e}")
        return None


def load_user_data_from_sheets():
    """Google Sheetsからユーザーデータを読み込む"""
    conn = get_gsheets_connection()
    if conn is None:
        return None
    
    try:
        df = conn.read(worksheet="UserData", ttl=5)
        if df is None or df.empty:
            return None
        
        user_id = get_user_id()
        user_row = df[df["user_id"] == user_id]
        
        if user_row.empty:
            return None
        
        row = user_row.iloc[0]
        return {
            "history": json.loads(row["history"]) if pd.notna(row["history"]) else {},
            "marked": json.loads(row["marked"]) if pd.notna(row["marked"]) else [],
            "stats": json.loads(row["stats"]) if pd.notna(row["stats"]) else {"correct": 0, "incorrect": 0, "total": 0},
            "last_question_index": int(row["last_question_index"]) if pd.notna(row.get("last_question_index")) else 0
        }
    except Exception as e:
        # ワークシートが存在しない場合など
        st.error(f"Google Sheets読み込みエラー: {e}")
        return None

def save_user_data_to_sheets():
    """Google Sheetsにユーザーデータを保存"""
    conn = get_gsheets_connection()
    if conn is None:
        return
    
    user_id = get_user_id()
    
    # 現在表示中の問題インデックスを取得
    filtered_indices = get_filtered_indices()
    if filtered_indices and st.session_state.current_index < len(filtered_indices):
        last_question_index = filtered_indices[st.session_state.current_index]
    else:
        last_question_index = 0
    
    # 保存データを準備
    save_data = {
        "user_id": user_id,
        "history": json.dumps({str(k): v for k, v in st.session_state.get("history", {}).items()}),
        "marked": json.dumps(list(st.session_state.get("marked_questions", set()))),
        "stats": json.dumps(st.session_state.get("current_session_stats", {"correct": 0, "incorrect": 0, "total": 0})),
        "last_question_index": last_question_index,
        "updated_at": datetime.now().isoformat()
    }
    
    try:
        # 既存データを読み込み
        try:
            df = conn.read(worksheet="UserData", ttl=0)
            if df is None or df.empty:
                df = pd.DataFrame(columns=["user_id", "history", "marked", "stats", "last_question_index", "updated_at"])
        except:
            df = pd.DataFrame(columns=["user_id", "history", "marked", "stats", "last_question_index", "updated_at"])
        
        # ユーザーの行を更新または追加
        if user_id in df["user_id"].values:
            idx = df[df["user_id"] == user_id].index[0]
            for col, val in save_data.items():
                df.at[idx, col] = val
        else:
            df = pd.concat([df, pd.DataFrame([save_data])], ignore_index=True)
        
        # 保存
        conn.update(worksheet="UserData", data=df)
        
    except Exception as e:
        st.toast(f"保存エラー: {e}", icon="⚠️")


# =============================================================================
# 問題データ関連
# =============================================================================

def load_questions():
    """問題データを読み込む"""
    json_path = Path(__file__).parent / "combined_output.json"
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_shuffled_options(question_idx):
    """問題の選択肢をシャッフルして返す（問題ごとに固定のシャッフル順）"""
    # 問題インデックスとユーザーIDをシードにして、毎回同じ順番にする
    # ただし問題を切り替えるたびに新しい順序
    key = f"option_order_{question_idx}"
    
    if key not in st.session_state:
        question = st.session_state.questions[question_idx]
        indices = list(range(len(question["options"])))
        # 問題インデックスをシードにしてシャッフル（セッション内では同じ順序）
        rng = random.Random(f"{st.session_state.get('shuffle_seed', 0)}_{question_idx}")
        rng.shuffle(indices)
        st.session_state[key] = indices
    
    return st.session_state[key]


def reset_option_orders():
    """選択肢の順序をリセット"""
    keys_to_remove = [k for k in st.session_state.keys() if k.startswith("option_order_")]
    for k in keys_to_remove:
        del st.session_state[k]
    # 新しいシャッフルシードを設定
    st.session_state.shuffle_seed = random.randint(0, 1000000)


# =============================================================================
# セッション状態管理
# =============================================================================

def initialize_session_state():
    """セッション状態を初期化"""
    if "questions" not in st.session_state:
        st.session_state.questions = load_questions()
    
    if "shuffle_seed" not in st.session_state:
        st.session_state.shuffle_seed = random.randint(0, 1000000)
    
    # Google Sheetsからデータを読み込み（初回のみ）
    if "data_loaded" not in st.session_state:
        st.session_state.data_loaded = True
        saved_data = load_user_data_from_sheets()
        
        if saved_data:
            st.session_state.history = {int(k): v for k, v in saved_data.get("history", {}).items()}
            st.session_state.marked_questions = set(saved_data.get("marked", []))
            st.session_state.current_session_stats = saved_data.get("stats", {"correct": 0, "incorrect": 0, "total": 0})
            # 最後に表示した問題インデックスを復元
            st.session_state.last_question_index = saved_data.get("last_question_index", 0)
    
    if "current_index" not in st.session_state:
        # 保存された問題インデックスがあればそれを使用
        last_idx = st.session_state.get("last_question_index", 0)
        st.session_state.current_index = last_idx
    if "answered" not in st.session_state:
        st.session_state.answered = False
    if "selected_options" not in st.session_state:
        st.session_state.selected_options = []
    if "marked_questions" not in st.session_state:
        st.session_state.marked_questions = set()
    if "history" not in st.session_state:
        st.session_state.history = {}
    if "shuffle_mode" not in st.session_state:
        st.session_state.shuffle_mode = False
    if "shuffled_indices" not in st.session_state:
        st.session_state.shuffled_indices = list(range(len(st.session_state.questions)))
    if "filter_modes" not in st.session_state:
        st.session_state.filter_modes = {"all"}  # 複数選択対応のためsetに変更
    if "current_session_stats" not in st.session_state:
        st.session_state.current_session_stats = {"correct": 0, "incorrect": 0, "total": 0}


def get_filtered_indices():
    """フィルターに基づいて問題インデックスを取得（複数フィルター対応）"""
    all_indices = st.session_state.shuffled_indices if st.session_state.shuffle_mode else list(range(len(st.session_state.questions)))
    
    filter_modes = st.session_state.filter_modes
    
    # 「すべて」が選択されている場合、または何も選択されていない場合は全問題を返す
    if "all" in filter_modes or not filter_modes:
        return all_indices
    
    # 複数フィルターの条件を満たす問題を収集（OR条件）
    result = set()
    
    if "marked" in filter_modes:
        result.update(i for i in all_indices if i in st.session_state.marked_questions)
    
    if "incorrect" in filter_modes:
        result.update(i for i in all_indices if i in st.session_state.history and not st.session_state.history[i]["correct"])
    
    if "unanswered" in filter_modes:
        result.update(i for i in all_indices if i not in st.session_state.history)
    
    # 元の順序を維持
    return [i for i in all_indices if i in result]


def count_correct_options(question):
    return sum(1 for opt in question["options"] if opt["status"] == "correct")


def check_answer_with_shuffle(question, selected_display_indices, option_order):
    """シャッフルされた選択肢での回答をチェック"""
    # 表示上のインデックスを元のインデックスに変換
    original_indices = [option_order[i] for i in selected_display_indices]
    correct_indices = {i for i, opt in enumerate(question["options"]) if opt["status"] == "correct"}
    return set(original_indices) == correct_indices


# =============================================================================
# ナビゲーション
# =============================================================================

def go_to_next_question():
    filtered_indices = get_filtered_indices()
    if st.session_state.current_index < len(filtered_indices) - 1:
        st.session_state.current_index += 1
    else:
        st.session_state.current_index = 0
    st.session_state.answered = False
    st.session_state.selected_options = []
    # 次の問題では新しい選択肢順序
    reset_option_orders()
    # 現在の問題をDBに保存
    save_user_data_to_sheets()
    st.rerun()


def go_to_prev_question():
    filtered_indices = get_filtered_indices()
    if st.session_state.current_index > 0:
        st.session_state.current_index -= 1
    else:
        st.session_state.current_index = len(filtered_indices) - 1
    st.session_state.answered = False
    st.session_state.selected_options = []
    reset_option_orders()
    # 現在の問題をDBに保存
    save_user_data_to_sheets()
    st.rerun()


# =============================================================================
# UI表示
# =============================================================================

def display_compact_header():
    """コンパクトなヘッダー"""
    stats = st.session_state.current_session_stats
    filtered_indices = get_filtered_indices()
    
    if not filtered_indices:
        return
    
    question_idx = filtered_indices[st.session_state.current_index]
    current_position = st.session_state.current_index + 1
    total_filtered = len(filtered_indices)
    
    cols = st.columns([2, 3])
    with cols[0]:
        is_marked = "⭐" if question_idx in st.session_state.marked_questions else ""
        st.markdown(f"**Q{question_idx + 1}** ({current_position}/{total_filtered}) {is_marked}")
    with cols[1]:
        if stats["total"] > 0:
            acc = int((stats["correct"] / stats["total"]) * 100)
            st.markdown(f"<span class='badge badge-stats'>{stats['correct']}/{stats['total']} ({acc}%)</span>", unsafe_allow_html=True)
    
    nav_cols = st.columns([1, 1, 2])
    with nav_cols[0]:
        if st.button("◀", key="prev_btn", use_container_width=True):
            go_to_prev_question()
    with nav_cols[1]:
        if st.button("▶", key="next_btn", use_container_width=True):
            go_to_next_question()
    with nav_cols[2]:
        correct_count = count_correct_options(st.session_state.questions[question_idx])
        if correct_count > 1:
            st.markdown(f"<span class='badge badge-count'>正解{correct_count}つ</span>", unsafe_allow_html=True)


def display_question():
    """問題を表示"""
    filtered_indices = get_filtered_indices()
    
    if not filtered_indices:
        st.warning("該当する問題がありません")
        st.markdown("---")
        st.markdown("**フィルターを変更してください：**")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 すべての問題を表示", use_container_width=True, type="primary"):
                st.session_state.filter_modes = {"all"}
                st.session_state.current_index = 0
                st.session_state.answered = False
                st.rerun()
        with col2:
            if st.button("⚙️ 設定タブへ", use_container_width=True):
                st.info("上の⚙️タブから問題フィルターを変更できます")
        
        # 現在のフィルター状態を表示
        st.caption(f"現在のフィルター: {', '.join(st.session_state.filter_modes)}")
        return
    
    if st.session_state.current_index >= len(filtered_indices):
        st.session_state.current_index = 0
    
    question_idx = filtered_indices[st.session_state.current_index]
    question = st.session_state.questions[question_idx]
    option_order = get_shuffled_options(question_idx)
    
    # 問題文
    st.markdown(f'<div class="question-box">{question["question"]}</div>', unsafe_allow_html=True)
    
    correct_count = count_correct_options(question)
    
    # お気に入りマークボタン（常に表示）
    mark_label = "⭐ お気に入り解除" if question_idx in st.session_state.marked_questions else "☆ お気に入り登録"
    if st.button(mark_label, use_container_width=True, key="mark_btn_top"):
        if question_idx in st.session_state.marked_questions:
            st.session_state.marked_questions.remove(question_idx)
        else:
            st.session_state.marked_questions.add(question_idx)
        save_user_data_to_sheets()
        st.rerun()
    
    if not st.session_state.answered:
        # シャッフルされた選択肢を表示
        shuffled_options = [question["options"][i] for i in option_order]
        
        if correct_count == 1:
            selected = st.radio(
                "選択:",
                options=range(len(shuffled_options)),
                format_func=lambda x: shuffled_options[x]["text"],
                key=f"radio_{question_idx}_{st.session_state.shuffle_seed}",
                label_visibility="collapsed"
            )
            st.session_state.selected_options = [selected] if selected is not None else []
        else:
            selected = []
            for i, opt in enumerate(shuffled_options):
                if st.checkbox(opt["text"], key=f"check_{question_idx}_{i}_{st.session_state.shuffle_seed}"):
                    selected.append(i)
            st.session_state.selected_options = selected
        
        if st.button("✓ 解答", type="primary", use_container_width=True):
            if st.session_state.selected_options:
                st.session_state.answered = True
                is_correct = check_answer_with_shuffle(question, st.session_state.selected_options, option_order)
                
                # 履歴更新
                if question_idx not in st.session_state.history:
                    st.session_state.history[question_idx] = {"correct": is_correct, "attempts": 1}
                else:
                    st.session_state.history[question_idx]["attempts"] += 1
                    st.session_state.history[question_idx]["correct"] = is_correct
                
                # 統計更新
                st.session_state.current_session_stats["total"] += 1
                if is_correct:
                    st.session_state.current_session_stats["correct"] += 1
                else:
                    st.session_state.current_session_stats["incorrect"] += 1
                
                # Google Sheetsに保存
                save_user_data_to_sheets()
                
                st.rerun()
            else:
                st.warning("選択してください")
    else:
        # 回答済み
        is_correct = check_answer_with_shuffle(question, st.session_state.selected_options, option_order)
        
        if is_correct:
            st.success("🎉 正解！")
        else:
            st.error("❌ 不正解")
        
        # シャッフル順で選択肢を表示
        for display_idx, original_idx in enumerate(option_order):
            opt = question["options"][original_idx]
            is_selected = display_idx in st.session_state.selected_options
            is_correct_opt = opt["status"] == "correct"
            
            if is_correct_opt:
                st.markdown(f'<div class="correct-answer">✅ {opt["text"]}{"【選択】" if is_selected else ""}</div>', unsafe_allow_html=True)
            elif is_selected:
                st.markdown(f'<div class="incorrect-answer">❌ {opt["text"]}【選択】</div>', unsafe_allow_html=True)
            else:
                st.write(f"　{opt['text']}")
        
        # 解説
        if question.get("explanation"):
            st.markdown(f'<div class="explanation-box">📖 <b>解説</b><br>{question["explanation"]}</div>', unsafe_allow_html=True)
        
        # ボタン
        btn_cols = st.columns(2)
        with btn_cols[0]:
            if st.button("🔄 もう一度", use_container_width=True):
                st.session_state.answered = False
                st.session_state.selected_options = []
                reset_option_orders()
                st.rerun()
        with btn_cols[1]:
            if st.button("次へ ▶", type="primary", use_container_width=True):
                go_to_next_question()


def display_settings():
    """設定タブ"""
    st.markdown("### ⚙️ 設定")
    
    # ユーザーID表示
    st.caption(f"ユーザーID: {get_user_id()}")
    
    # 問題フィルター（複数選択対応）
    st.markdown("**問題フィルター:**")
    
    filter_counts = {
        "all": len(st.session_state.questions),
        "marked": len(st.session_state.marked_questions),
        "incorrect": len([i for i in st.session_state.history if not st.session_state.history[i]['correct']]),
        "unanswered": len(st.session_state.questions) - len(st.session_state.history)
    }
    
    filter_labels = {
        "all": f"すべて ({filter_counts['all']})",
        "marked": f"⭐マーク ({filter_counts['marked']})",
        "incorrect": f"❌不正解 ({filter_counts['incorrect']})",
        "unanswered": f"未回答 ({filter_counts['unanswered']})"
    }
    
    # 現在の選択状態を取得
    current_modes = st.session_state.filter_modes.copy()
    is_all_mode = "all" in current_modes
    
    # 「すべて」のチェックボックス
    all_checked = st.checkbox(
        filter_labels["all"],
        value=is_all_mode,
        key="filter_all"
    )
    
    # その他のフィルター（「すべて」がチェックされている場合は無効化しない）
    col1, col2 = st.columns(2)
    with col1:
        marked_checked = st.checkbox(
            filter_labels["marked"],
            value="marked" in current_modes,
            key="filter_marked"
        )
    with col2:
        incorrect_checked = st.checkbox(
            filter_labels["incorrect"],
            value="incorrect" in current_modes,
            key="filter_incorrect"
        )
    
    unanswered_checked = st.checkbox(
        filter_labels["unanswered"],
        value="unanswered" in current_modes,
        key="filter_unanswered"
    )
    
    # フィルターの更新
    new_modes = set()
    
    # 個別フィルターが選択された場合は「すべて」を解除
    has_specific_filter = marked_checked or incorrect_checked or unanswered_checked
    
    if all_checked and not has_specific_filter:
        # 「すべて」のみがチェックされている場合
        new_modes.add("all")
    elif has_specific_filter:
        # 個別フィルターが1つ以上チェックされている場合
        if marked_checked:
            new_modes.add("marked")
        if incorrect_checked:
            new_modes.add("incorrect")
        if unanswered_checked:
            new_modes.add("unanswered")
    else:
        # 何も選択されていない場合は「すべて」を選択
        new_modes.add("all")
    
    if new_modes != st.session_state.filter_modes:
        st.session_state.filter_modes = new_modes
        st.session_state.current_index = 0
        st.session_state.answered = False
        st.rerun()
    
    # 現在のフィルター結果を表示
    filtered_count = len(get_filtered_indices())
    st.caption(f"フィルター結果: {filtered_count}問")
    
    shuffle = st.toggle("🔀 問題順シャッフル", value=st.session_state.shuffle_mode)
    if shuffle != st.session_state.shuffle_mode:
        st.session_state.shuffle_mode = shuffle
        if shuffle:
            st.session_state.shuffled_indices = list(range(len(st.session_state.questions)))
            random.shuffle(st.session_state.shuffled_indices)
        st.session_state.current_index = 0
        st.session_state.answered = False
        st.rerun()
    
    st.divider()
    
    st.markdown("### 🔢 問題に移動")
    filtered_indices = get_filtered_indices()
    if filtered_indices:
        jump_to = st.number_input(
            "問題番号",
            min_value=1,
            max_value=len(st.session_state.questions),
            value=filtered_indices[st.session_state.current_index] + 1,
            step=1
        )
        if st.button("移動", use_container_width=True):
            target_idx = jump_to - 1
            if target_idx in filtered_indices:
                st.session_state.current_index = filtered_indices.index(target_idx)
            else:
                st.session_state.filter_mode = "all"
                st.session_state.current_index = target_idx
            st.session_state.answered = False
            reset_option_orders()
            save_user_data_to_sheets()
            st.rerun()
    
    st.divider()
    
    st.markdown("### 🗑️ リセット")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("履歴クリア", use_container_width=True):
            st.session_state.history = {}
            st.session_state.current_session_stats = {"correct": 0, "incorrect": 0, "total": 0}
            save_user_data_to_sheets()
            st.rerun()
    with col2:
        if st.button("マーククリア", use_container_width=True):
            st.session_state.marked_questions = set()
            save_user_data_to_sheets()
            st.rerun()


def display_marked_list():
    """マーク一覧"""
    if not st.session_state.marked_questions:
        st.info("マークした問題はありません")
        return
    
    st.markdown(f"### ⭐ マーク済み ({len(st.session_state.marked_questions)}問)")
    
    for idx in sorted(st.session_state.marked_questions):
        q = st.session_state.questions[idx]
        short_q = q['question'][:40] + "..." if len(q['question']) > 40 else q['question']
        
        col1, col2 = st.columns([4, 1])
        with col1:
            st.write(f"**Q{idx+1}**: {short_q}")
        with col2:
            if st.button("Go", key=f"go_{idx}"):
                st.session_state.filter_mode = "all"
                st.session_state.current_index = idx
                st.session_state.answered = False
                reset_option_orders()
                save_user_data_to_sheets()
                st.rerun()


def display_stats():
    """統計"""
    total = len(st.session_state.questions)
    answered = len(st.session_state.history)
    correct = sum(1 for h in st.session_state.history.values() if h["correct"])
    marked = len(st.session_state.marked_questions)
    
    st.markdown("### 📊 統計")
    
    cols = st.columns(4)
    cols[0].metric("総数", total)
    cols[1].metric("回答", answered)
    cols[2].metric("正解", correct)
    cols[3].metric("⭐", marked)
    
    if answered > 0:
        acc = correct / answered
        st.progress(acc, text=f"正答率: {acc*100:.1f}%")
    
    st.markdown("#### 今回のセッション")
    stats = st.session_state.current_session_stats
    if stats["total"] > 0:
        cols = st.columns(3)
        cols[0].metric("回答数", stats["total"])
        cols[1].metric("正解", stats["correct"])
        cols[2].metric("正答率", f"{stats['correct']/stats['total']*100:.0f}%")


def main():
    initialize_session_state()
    get_user_id()  # URLにユーザーIDを設定
    
    display_compact_header()
    
    tab1, tab2, tab3 = st.tabs(["📝", "⭐", "⚙️"])
    
    with tab1:
        display_question()
    
    with tab2:
        display_marked_list()
        st.divider()
        display_stats()
    
    with tab3:
        display_settings()


if __name__ == "__main__":
    main()
