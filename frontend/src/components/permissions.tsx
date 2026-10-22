"use client";
import { useEffect, useState } from "react";
import {
  aborted,
  api,
  listAll,
  message,
  workspacePath,
  type Collection,
  type Grant,
  type Member,
} from "../lib/api";
import { Icon } from "./icons";
export function Permissions({
  identity,
  workspace,
  collection,
  onChange,
}: {
  identity: string;
  workspace: string;
  collection: Collection;
  onChange: () => void;
}) {
  const [members, setMembers] = useState<Member[]>([]);
  const [grants, setGrants] = useState<Grant[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const base = workspacePath(workspace, `/collections/${collection.id}/grants`);
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      listAll<Member>(
        workspacePath(workspace, `/members?collection_id=${collection.id}`),
        identity,
        controller.signal,
      ),
      listAll<Grant>(base, identity, controller.signal),
    ])
      .then(([people, access]) => {
        if (!controller.signal.aborted) {
          setMembers(people);
          setGrants(access);
        }
      })
      .catch((e) => {
        if (!aborted(e)) setError(message(e));
      });
    return () => controller.abort();
  }, [base, identity, workspace, collection.id]);
  async function update(member: Member, permission: string) {
    setBusy(member.membership_id);
    setError("");
    setNotice("");
    try {
      await api(
        `${base}/${member.membership_id}`,
        identity,
        permission
          ? { method: "PUT", body: JSON.stringify({ permission }) }
          : { method: "DELETE" },
      );
      setGrants((rows) => [
        ...rows.filter((row) => row.membership_id !== member.membership_id),
        ...(permission
          ? [
              {
                membership_id: member.membership_id,
                permission: permission as Grant["permission"],
              },
            ]
          : []),
      ]);
      setNotice(`Access updated for ${member.display_name}.`);
      onChange();
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy("");
    }
  }
  return (
    <section className="view-enter">
      <div className="section-heading">
        <p className="eyebrow">A little housekeeping</p>
        <h1>
          Who can see what<span className="pencil-dot">?</span>
        </h1>
        <p className="muted">
          Manage access to <strong>{collection.name}</strong>. Permissions are
          enforced by the API.
        </p>
      </div>
      <div className="notice">
        <Icon name="shield" />
        <p>
          Workspace owners and admins retain management access. A person’s saved
          questions and answers remain private to them.
        </p>
      </div>
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="notice success" role="status">
          {notice}
        </p>
      )}
      <div className="permission-list">
        {members.map((member) => (
          <div className="permission-row" key={member.membership_id}>
            <div className="avatar">{member.display_name.charAt(0)}</div>
            <div className="file-info">
              <strong>{member.display_name}</strong>
              <span>{member.role}</span>
            </div>
            {member.role === "owner" || member.role === "admin" ? (
              <span className="status-pill">Workspace {member.role}</span>
            ) : (
              <select
                aria-label={`Access for ${member.display_name}`}
                value={
                  grants.find(
                    (row) => row.membership_id === member.membership_id,
                  )?.permission ?? ""
                }
                disabled={!!busy}
                onChange={(e) => void update(member, e.target.value)}
              >
                <option value="">No access</option>
                <option value="read">Read</option>
                <option value="write">Read & upload</option>
                <option value="manage">Manage collection</option>
              </select>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
