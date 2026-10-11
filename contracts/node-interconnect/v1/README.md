# Node interconnect facts, v1

`node.interconnect/v1` is a bounded, read-only projection of one compute node's
hardware relationships. It is a view over native observations, not a scheduler,
asset database, or utilization stream. The producer records a node-local
observation from NVIDIA topology, Slurm GRES mapping, Linux NUMA data and the
site's fabric registration. The Portal/site reader and `sai-cli` use the same
allowlist and parser. Pilot consumes this object without parsing terminal text.

The producer MUST verify the device identity mapping before publishing. A Slurm
GRES index, Linux CPU ID and NVIDIA index are different namespaces until the
published mapping proves their relationship. No consumer may infer a link from
index order, a model name, node naming, or a count. An unavailable mapping is
`status=unavailable`, never an empty topology.

A record contains:

- `node`, `cluster`, and an observation interval (`observed_at`, `expires_at`);
- Slurm CPU dimensions and explicit NUMA domains with CPU IDs;
- GPU records with Slurm GRES index, NUMA domain and mapped CPU IDs;
- a complete symmetric GPU-to-GPU matrix, where `kind` is a native path class
  such as `NV2`, `PIX`, `PXB`, `PHB`, `NODE` or `SYS`;
- optional NIC records, each with native GPU path classes, a safe fabric peer
  reference and link rate.

The public projection does not contain GPU UUIDs, PCI addresses, device minors,
serials, switch GUIDs, raw `nvidia-smi` output, or cable labels. The site may
retain those in its operator evidence. Fabric peers are opaque references with unknown device type,
not a promise of end-to-end route health or available bandwidth.

The record is independent of a job allocation. A job response joins the record
only for its currently allocated nodes and retains the job's native CPU/GPU
allocation as a separate fact. Expired, withdrawn, changed or unauthorized
records are discarded. Web, TUI and Agent render a compact relationship view;
exact IDs remain available in structured data and deliberate detail, rather than
printing every CPU thread in the default view.

## Sources and ownership

The site operator owns collection and publication. Slurm remains authoritative
for job allocation. The site-read gateway verifies authorization and reads the
current published record; it does not SSH to compute nodes or run `slurmd -G`
for every refresh. Local CLI may read the same root-published record when it is
present on the login/compute environment. A missing record is an honest unknown.

The first implementation uses an atomic, root-owned file per node under the
existing `/opt/sai/runtime` publication. A daemon, graph database and new
per-node mount are not required. Collection tools must be bounded and run by
site operations, outside user/runtime readers. Records are timestamped and
expire so a stale topology cannot masquerade as current hardware.

## Observation and publication contract

Records describe a bounded observation, not current link health. `boot_time` and
`slurmd_start_time` bind the device mapping to one native generation. They cannot
detect an in-place cable move or a configuration rewrite; the site publisher must
withdraw or replace the record after those changes. Expiry is checked when the
file is read, after generation lookup and on each consumer arrival. GUI consumers
must also stop displaying a current mapping once the record expires while open.

Linux CPU/package IDs are an independent namespace and may be sparse. Slurm can
be configured to treat NUMA domains as sockets; consumers must not label Slurm
socket dimensions as physical CPU packages. GRES CPU IDs are Slurm IDs, whereas
`numa[].linux_cpu_ids` are Linux IDs. The two are never joined by numeric equality.

GPU `pcie_path` is optional, and contains only observed root/bridge ancestry.
NIC peers use opaque `endpoint-*` references. No device type is inferred from an
IB GUID or display name. Optional `fabric_links` contains observed active edges;
a job projection retains only edges between the selected nodes' recorded NIC
peers. Missing intermediate routes stay unknown. A path class or link rate does
not prove available bandwidth, application traffic or performance.

`scripts/ops/normalize_node_interconnect.py` transforms private native captures
into one public-safe record without executing native probes. Input capture JSON
contains node identity, Slurm node JSON, observation time and lscpu CPU JSON. GPU
nodes additionally supply NVIDIA matrix, index/PCI CSV, XML and a GRES capture
bound to the same node boot/Slurm generation. Optional PCIe/fabric capture includes
its own matching native node generation. NIC captures are keyed by the actual
HCA name and include its sysfs node GUID; NVIDIA's NIC legend binds that device
to the display index. Array order and numeric device-name suffixes are not maps.

Publish only validated records with reviewed expiry through the existing runtime
owner: root-owned directory 0755, regular files 0644, atomic replacement and one
shared publication for login/compute readers. Withdrawal removes the selected
record; there is no previous-record fallback. The default read location is
`/opt/sai/runtime/topology/<node>.json`. Site gateway deployment must make the same
reviewed records available in that role's existing runtime, without per-command
mounts or a new authorization service. Production publication and update ownership
remain separate from local source validation.
