"""COMMAND_DECK_TRUTH_V1 (masterplan Horizon 1, bundle 7) — RED-first contract tests.

Pure static-scan checks over command-deck source text: fiction/jargon/debug tokens are a hard
block, panels must be data-bound to the real profile, honest empty-states must be present, and the
profile subsystem must be real code. Fixtures are synthetic strings (snapshot law — tests never
read or mutate the live source).
"""
from __future__ import annotations

from dimwit.pipelines.command_deck import (
    FICTION_TOKENS,
    HONEST_FALLBACK_TOKENS,
    MIN_PROFILE_HITS,
    PROGRESSION_MIN_HITS,
    check_honest_empty_states,
    check_profile_subsystem,
    check_reads_earned_progression,
    check_reads_real_profile,
    scan_ui_fiction,
)


# the pre-fix command deck (the real fiction that shipped before bundle 7) — the anti-weakening golden
FICTION_HUD = r'''
Text(PC->IsMeleeOnly() ? TEXT("READY CHECK: melee-safe staging") : TEXT("READY CHECK: armed"), ...);
Text(TEXT("Live sandbox queue"), ...);
Text(TEXT("ranked playlists staged  |  bot combat available  |  shell deploy route armed"), ...);
Text(TEXT("social, rank, stats, and settings channels synchronized"), ...);
Text(TEXT("WANE-ADEPT III"), ...);
Text(TEXT("1990 / 2200"), ...);
const TCHAR* Rows[5] = { TEXT("01  Zythan_Prime 2480"), TEXT("02  ApexKelous 2310"),
  TEXT("03  Therak_77 2155"), TEXT("04  you 1990"), TEXT("05  NexorByte 1840") };
Text(TEXT("weekly board refresh armed"), ...);
const TCHAR* CardValue[3] = { TEXT("party open"), TEXT("1.42 K/D"), TEXT("high / 90 FOV") };
'''

# the fixed command deck: data-bound to the real profile, honest empty-states, no fiction
REAL_HUD = r'''
UWanefallProfileSubsystem* Sub = GetProfileSubsystem();
const FWanefallPlayerProfile& P = Sub->GetProfile();
const FWanefallRankBucket* Arena = Sub->ArenaRank();
Text(Arena && !Arena->bProvisional ? RankLine(Arena) : TEXT("UNRANKED  PLACEMENT 0/5"), ...);
if (Sub->TopLeaderboard().Num() == 0) { Text(TEXT("NO LOCAL RECORDS YET  PLAY A MATCH"), ...); }
const FWanefallModeStat* ArenaStat = P.ModeStats.Find(TEXT("4v4 Arena"));
Text(ArenaStat ? FString::Printf(TEXT("%.2f K/D"), ArenaStat->KD()) : TEXT("—"), ...);
Text(TEXT("READY CHECK: STAGING AREA"), ...);
Text(TEXT("LOCAL BOT MATCH"), ...);
for (tab) { if (!bImplemented) Text(TEXT("COMING SOON"), ...); }
Text(FString::Printf(TEXT("ACCOUNT LEVEL %d"), P.AccountLevel), ...);
'''

REAL_SUBSYSTEM_H = r'''
UCLASS()
class WANEFALLGREYBOX_API UWanefallProfileSubsystem : public UGameInstanceSubsystem
{
    GENERATED_BODY()
public:
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    const FWanefallPlayerProfile& GetProfile() const { return Profile; }
    const FWanefallRankBucket* ArenaRank() const;
};
'''

REAL_SUBSYSTEM_CPP = r'''
void UWanefallProfileSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
    FString Json;
    if (FFileHelper::LoadFileToString(Json, *Path) && Profile.FromJson(Json)) { return; }
    Profile = FWanefallPlayerProfile::MakeDefault(TEXT("local"), TEXT("Operative"), TEXT(""));
}
'''


# ------------------------------------------------------------------ fiction lint

def test_fiction_hud_fails_lint():
    r = scan_ui_fiction(FICTION_HUD)
    assert not r["passed"]
    assert "melee-safe" in r["hits"]
    assert "zythan_prime" in r["hits"]
    assert "1.42 k/d" in r["hits"]


def test_real_hud_passes_lint():
    r = scan_ui_fiction(REAL_HUD)
    assert r["passed"], r["issues"]


def test_empty_source_fails_lint():
    assert not scan_ui_fiction("")["passed"]


def test_each_fiction_token_is_caught():
    for token in FICTION_TOKENS:
        assert not scan_ui_fiction(f'Text(TEXT("{token}"));')["passed"], token


# ------------------------------------------------------------------ real-profile binding

def test_real_hud_is_data_bound():
    assert check_reads_real_profile(REAL_HUD)["passed"]


def test_fiction_hud_not_data_bound():
    # the pre-fix HUD references no profile accessors
    assert not check_reads_real_profile(FICTION_HUD)["passed"]


def test_too_few_accessors_fails():
    text = "GetProfile() only"          # 1 accessor < MIN_PROFILE_HITS
    r = check_reads_real_profile(text)
    assert not r["passed"]
    assert len(r["found"]) < MIN_PROFILE_HITS


def test_comment_only_profile_tokens_fail():
    comments = "\n".join(f"// {token}" for token in (
        "ProfileSubsystem", "GetProfile", "RankState", "ModeStats", "KD(", "TierName"
    ))
    assert not check_reads_real_profile(comments)["passed"]


# ------------------------------------------------------------------ honest empty states

def test_real_hud_has_honest_states():
    assert check_honest_empty_states(REAL_HUD)["passed"]


def test_missing_honest_state_fails():
    text = REAL_HUD.replace("UNRANKED", "WANE-ADEPT III")
    r = check_honest_empty_states(text)
    assert not r["passed"]
    assert "UNRANKED" in r["missing"]


def test_comment_only_honest_states_fail():
    comments = "// UNRANKED\n/* NO LOCAL RECORDS and COMING SOON */"
    result = check_honest_empty_states(comments)
    assert not result["passed"]
    assert set(result["missing"]) == set(HONEST_FALLBACK_TOKENS)


# ------------------------------------------------------------------ profile subsystem

def test_real_subsystem_passes():
    assert check_profile_subsystem(REAL_SUBSYSTEM_H, REAL_SUBSYSTEM_CPP)["passed"]


def test_missing_subsystem_fails():
    assert not check_profile_subsystem("", "")["passed"]


def test_subsystem_without_default_fallback_fails():
    cpp = "void Init() { Profile.FromJson(Json); }"     # no MakeDefault
    assert not check_profile_subsystem(REAL_SUBSYSTEM_H, cpp)["passed"]


def test_non_subsystem_class_fails():
    h = "class UWanefallProfileSubsystem : public UObject { const FWanefallPlayerProfile& GetProfile(); };"
    assert not check_profile_subsystem(h, REAL_SUBSYSTEM_CPP)["passed"]


# ------------------------------------------------------------------ earned-progression readout (Task 7)

# a command deck that reads the REAL progression subsystem challenge book + has an honest empty state
EARNED_HUD = r'''
UWanefallProgressionSubsystem* ProgressionSubsystem = GI->GetSubsystem<UWanefallProgressionSubsystem>();
Text(TEXT("CHALLENGES"), Pad + 18.0f, ChalY, Teal, 0.95f);
if (ProgressionSubsystem && ProgressionSubsystem->Challenges().Challenges.Num() > 0) {
    const TArray<FWanefallChallenge>& Chals = ProgressionSubsystem->Challenges().Challenges;
    for (int32 i = 0; i < Shown; ++i) {
        const FWanefallChallenge& C = Chals[i];
        Text(FString::Printf(TEXT("%s  %d/%d"), *C.Desc, C.Progress, C.Target), Pad, RowY, White, 0.78f);
    }
} else {
    Text(TEXT("NO ACTIVE CHALLENGES"), Pad + 18.0f, ChalY + 30.0f, White, 0.82f);
}
'''


def test_earned_hud_reads_progression():
    r = check_reads_earned_progression(EARNED_HUD)
    assert r["passed"], r["issues"]
    assert len(r["found"]) >= PROGRESSION_MIN_HITS


def test_hud_without_challenge_readout_fails():
    # the pre-Task-7 deck referenced no progression subsystem at all
    assert not check_reads_earned_progression(REAL_HUD)["passed"]


def test_progression_readout_without_empty_state_fails():
    text = EARNED_HUD.replace("NO ACTIVE CHALLENGES", "WANE-ELITE STREAK")
    r = check_reads_earned_progression(text)
    assert not r["passed"]


def test_progression_readout_without_live_progress_fails():
    # binds the subsystem but never renders C.Progress/C.Target -> could be faking a static bar
    text = EARNED_HUD.replace("*C.Desc, C.Progress, C.Target", '"daily kills"')
    r = check_reads_earned_progression(text)
    assert not r["passed"]


def test_empty_source_fails_progression():
    assert not check_reads_earned_progression("")["passed"]


def test_comment_only_progression_contract_fails():
    comments = """
    // ProgressionSubsystem Challenges() FWanefallChallenge
    /* CHALLENGES C.Progress C.Target NO ACTIVE CHALLENGES */
    """
    assert not check_reads_earned_progression(comments)["passed"]


# ------------------------------------------------------------------ ratchet

def test_fiction_blocklist_is_ratchet():
    """The fiction blocklist may only grow. These tokens are load-bearing and must never be
    removed (masterplan: the 'melee-safe staging' class of leak stays a blocker forever)."""
    for required in ("melee-safe", "sandbox", "synchronized", "zythan_prime", "1.42 k/d",
                     "todo", "debug", "placeholder"):
        assert required in FICTION_TOKENS, required
    assert MIN_PROFILE_HITS >= 3
    assert "UNRANKED" in HONEST_FALLBACK_TOKENS
