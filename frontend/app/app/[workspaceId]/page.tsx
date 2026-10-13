import { SessionGate } from '@/components/live/session';
import { WorkspaceOverview } from '@/components/live/workspace';
export default async function WorkspacePage({ params }: { params: Promise<{ workspaceId: string }> }) {
  const { workspaceId } = await params;
  return <SessionGate><WorkspaceOverview workspaceId={workspaceId} /></SessionGate>;
}
