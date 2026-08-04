return {
    schema_version = 1,
    revision = "example-1",
    generated_at = 1785823200,
    expires_at = 4102444800,
    gpu_per_node_multiple = 4,
    gpu_multiple_exempt_qos = {
        ["gpu-special"] = true,
    },
    personal_accounts = {
        ["alice"] = "personal-alice",
    },
    org_accounts = {
        ["org-example"] = "org-example",
    },
    project_accounts = {
        ["org-example/proj-research"] = "proj-research",
        ["org-example/proj-standard"] = "org-example",
    },
    home_aliases = {
        ["alice/workdir_org-example"] = "org-example",
    },
}
