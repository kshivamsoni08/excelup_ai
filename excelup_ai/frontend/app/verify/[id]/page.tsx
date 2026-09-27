"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { BadgeCheck, ShieldCheck, ShieldX, Fingerprint } from "lucide-react";
import { api } from "@/lib/api";

type VerifyResult = {
  found: boolean;
  payload?: any;
  issued_at?: string;
  status?: string;
  signature_valid?: boolean;
  merkle_root?: string;
  merkle_proof_valid?: boolean | null;
  authentic?: boolean;
};

export default function VerifyPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const { data, isLoading } = useQuery({
    queryKey: ["verify", id],
    queryFn: () => api<VerifyResult>(`/verify/${id}`),
    enabled: !!id,
  });

  return (
    <div className="flex min-h-screen items-center justify-center bg-stone-100 p-6">
      <div className="w-full max-w-xl">
        <div className="mb-4 flex items-center gap-2">
          <Fingerprint className="h-6 w-6 text-primary-800" />
          <span className="text-lg font-bold text-primary-950">ExcelUp AI Credential Verification</span>
        </div>

        {isLoading && <div className="card p-10 text-center text-stone-400">Verifying…</div>}

        {data && !data.found && (
          <div className="card border-red-300 bg-red-50 p-6">
            <div className="flex items-center gap-3 text-red-800">
              <ShieldX className="h-8 w-8" />
              <b className="text-lg">Credential not found</b>
            </div>
          </div>
        )}

        {data?.found && (
          <>
            <div className={`card p-6 ${data.authentic ? "border-primary-300 bg-primary-50" : "border-red-300 bg-red-50"}`}>
              <div className="flex items-center gap-3">
                {data.authentic
                  ? <BadgeCheck className="h-10 w-10 text-primary-700" />
                  : <ShieldX className="h-10 w-10 text-red-600" />}
                <div>
                  <div className={`text-lg font-bold ${data.authentic ? "text-primary-900" : "text-red-800"}`}>
                    {data.authentic ? "Authentic - signature & Merkle proof valid" : "TAMPERED - verification failed"}
                  </div>
                  <div className="text-xs text-stone-500">Issued {new Date(data.issued_at!).toLocaleString()}</div>
                </div>
              </div>
            </div>

            <div className="card mt-4 space-y-2 p-6 text-sm">
              <h3 className="font-semibold text-stone-800">Credential payload (signed)</h3>
              {Object.entries(data.payload ?? {}).map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4 border-b border-stone-50 py-1">
                  <span className="capitalize text-stone-500">{k.replace(/_/g, " ")}</span>
                  <b className="text-right">{Array.isArray(v) ? v.join(", ") : String(v)}</b>
                </div>
              ))}
              <div className="mt-3 space-y-1 text-xs">
                <div className="flex items-center gap-2">
                  {data.signature_valid ? <ShieldCheck className="h-4 w-4 text-primary-700" /> : <ShieldX className="h-4 w-4 text-red-600" />}
                  Ed25519 signature: <b>{data.signature_valid ? "valid" : "INVALID"}</b>
                </div>
                <div className="flex items-center gap-2">
                  {data.merkle_proof_valid ? <ShieldCheck className="h-4 w-4 text-primary-700" /> : data.merkle_proof_valid === false ? <ShieldX className="h-4 w-4 text-red-600" /> : <ShieldCheck className="h-4 w-4 text-stone-400" />}
                  Merkle proof: <b>{data.merkle_proof_valid == null ? "not batched" : data.merkle_proof_valid ? "valid" : "INVALID"}</b>
                </div>
                <div className="truncate text-stone-400">root: {data.merkle_root}</div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
