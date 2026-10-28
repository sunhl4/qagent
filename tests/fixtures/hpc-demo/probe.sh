#!/bin/bash
#SBATCH --job-name=probe-e2e
#SBATCH --output=probe_e2e-%j.out
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --time=00:03:00
echo "probe e2e start $(date -Is)"
hostname
echo "nproc=$(nproc)"
echo "slurm_job_id=${SLURM_JOB_ID:-unset}"
echo "probe e2e end $(date -Is)"
