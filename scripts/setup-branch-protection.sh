#!/usr/bin/env bash
#
# One-time setup of the server-side guardrails that the committed config files
# can't enforce on their own:
#
#   1. A `production` deployment environment with the maintainer as a required
#      reviewer, restricted to protected branches. This is what makes the
#      FLY_API_TOKEN safe to store: it's an *environment* secret, only readable
#      by jobs that target `production`, and every deploy pauses for approval.
#   2. (Optional) the FLY_API_TOKEN environment secret itself.
#   3. A branch ruleset on the default branch that requires a reviewed PR,
#      requires CODEOWNERS review, and requires CI status checks to pass.
#
# Re-running is safe: the environment PUT is idempotent and the ruleset is
# replaced if one with the same name already exists.
#
# Requires the GitHub CLI authenticated as a repo admin:
#     gh auth login
# then:
#     ./scripts/setup-branch-protection.sh
#
set -euo pipefail

# --- Config -----------------------------------------------------------------
# Code owner / required reviewer. Must be a collaborator with at least write.
OWNER_LOGIN="caseyjmorton"
ENVIRONMENT="production"
RULESET_NAME="main protection"
# CI checks that must pass before merge. These are the job names from
# .github/workflows/*.yml and run on every PR. Add more (e.g. "analyze",
# "review") once you've confirmed their exact check-run names appear on a PR.
REQUIRED_CHECKS=("build-test" "syntax")
# ---------------------------------------------------------------------------

# Locate gh (PATH, or via mise if installed there).
if command -v gh >/dev/null 2>&1; then
  GH=(gh)
elif command -v mise >/dev/null 2>&1 && mise exec -- gh --version >/dev/null 2>&1; then
  GH=(mise exec -- gh)
else
  echo "error: GitHub CLI (gh) not found. Install it, then 'gh auth login'." >&2
  exit 1
fi

if ! "${GH[@]}" auth status >/dev/null 2>&1; then
  echo "error: not authenticated. Run 'gh auth login' as a repo admin first." >&2
  exit 1
fi

# Resolve owner/repo from this repo's origin.
REPO="$("${GH[@]}" repo view --json nameWithOwner --jq .nameWithOwner)"
DEFAULT_BRANCH="$("${GH[@]}" repo view --json defaultBranchRef --jq .defaultBranchRef.name)"
REVIEWER_ID="$("${GH[@]}" api "users/${OWNER_LOGIN}" --jq .id)"

echo "Repo:            ${REPO}"
echo "Default branch:  ${DEFAULT_BRANCH}"
echo "Reviewer:        ${OWNER_LOGIN} (id ${REVIEWER_ID})"
echo "Required checks: ${REQUIRED_CHECKS[*]}"
echo
read -r -p "Apply this configuration to ${REPO}? [y/N] " confirm
[[ "${confirm}" == "y" || "${confirm}" == "Y" ]] || { echo "Aborted."; exit 0; }

# --- 1. production environment + required reviewer ---------------------------
echo "==> Creating/updating '${ENVIRONMENT}' environment with required reviewer..."
"${GH[@]}" api --method PUT "repos/${REPO}/environments/${ENVIRONMENT}" --input - >/dev/null <<JSON
{
  "wait_timer": 0,
  "reviewers": [{ "type": "User", "id": ${REVIEWER_ID} }],
  "deployment_branch_policy": { "protected_branches": true, "custom_branch_policies": false }
}
JSON
echo "    done."

# --- 2. FLY_API_TOKEN environment secret (optional) -------------------------
echo
read -r -p "Set the FLY_API_TOKEN secret on '${ENVIRONMENT}' now? [y/N] " set_secret
if [[ "${set_secret}" == "y" || "${set_secret}" == "Y" ]]; then
  echo "Get a deploy token with: flyctl tokens create deploy -a mr-radar"
  "${GH[@]}" secret set FLY_API_TOKEN --env "${ENVIRONMENT}" --repo "${REPO}"
  echo "    secret set."
else
  echo "    skipped — set it later with:"
  echo "      gh secret set FLY_API_TOKEN --env ${ENVIRONMENT} --repo ${REPO}"
fi

# --- 3. Branch ruleset ------------------------------------------------------
# bypass: the repo Admin role (built-in id 5) may bypass, but only via a pull
# request ("pull_request" mode), never a direct push to the default branch.
# This lets the sole maintainer merge their own PRs (GitHub forbids approving
# your own PR) while still forcing every change through a PR.
echo
echo "==> Configuring branch ruleset '${RULESET_NAME}'..."

required_checks_json="$(printf '%s\n' "${REQUIRED_CHECKS[@]}" \
  | awk 'BEGIN{c=""} {printf "%s{\"context\":\"%s\"}", c, $0; c=","}')"

ruleset_payload="$(cat <<JSON
{
  "name": "${RULESET_NAME}",
  "target": "branch",
  "enforcement": "active",
  "bypass_actors": [
    { "actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "pull_request" }
  ],
  "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] } },
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 1,
        "require_code_owner_review": true,
        "dismiss_stale_reviews_on_push": true,
        "require_last_push_approval": true,
        "required_review_thread_resolution": false,
        "allowed_merge_methods": ["squash", "merge", "rebase"]
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "required_status_checks": [${required_checks_json}]
      }
    }
  ]
}
JSON
)"

existing_id="$("${GH[@]}" api "repos/${REPO}/rulesets" --jq \
  ".[] | select(.name==\"${RULESET_NAME}\") | .id" 2>/dev/null | head -n1 || true)"

if [[ -n "${existing_id}" ]]; then
  echo "    updating existing ruleset #${existing_id}..."
  echo "${ruleset_payload}" | "${GH[@]}" api --method PUT "repos/${REPO}/rulesets/${existing_id}" --input - >/dev/null
else
  echo "    creating new ruleset..."
  echo "${ruleset_payload}" | "${GH[@]}" api --method POST "repos/${REPO}/rulesets" --input - >/dev/null
fi
echo "    done."

echo
echo "All set. Verify in the GitHub UI:"
echo "  Settings > Environments > ${ENVIRONMENT}  (required reviewer + FLY_API_TOKEN)"
echo "  Settings > Rules > Rulesets > ${RULESET_NAME}"
