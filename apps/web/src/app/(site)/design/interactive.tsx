"use client";

import { useState } from "react";
import { PanelRight } from "lucide-react";
import { Button, Dialog, Sheet, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui";

export function TabsDemo() {
  return (
    <Tabs defaultValue="itinerary">
      <TabsList label="Trip sections">
        <TabsTrigger value="itinerary">Itinerary</TabsTrigger>
        <TabsTrigger value="providers">Providers</TabsTrigger>
        <TabsTrigger value="flows">Flows</TabsTrigger>
      </TabsList>
      <TabsContent value="itinerary">
        <p className="text-sm text-muted-foreground">Day-by-day plan: matches, trainings, experiences.</p>
      </TabsContent>
      <TabsContent value="providers">
        <p className="text-sm text-muted-foreground">Hotel, bus, referees — with confirmation status.</p>
      </TabsContent>
      <TabsContent value="flows">
        <p className="text-sm text-muted-foreground">Executions running for this trip.</p>
      </TabsContent>
    </Tabs>
  );
}

export function OverlayDemo() {
  const [dialog, setDialog] = useState(false);
  const [sheet, setSheet] = useState(false);
  return (
    <div className="flex flex-wrap gap-2">
      <Button variant="secondary" onClick={() => setDialog(true)}>
        Open dialog
      </Button>
      <Button variant="secondary" onClick={() => setSheet(true)}>
        <PanelRight />
        Open sheet
      </Button>
      <Dialog
        open={dialog}
        onClose={() => setDialog(false)}
        title="Approve proposal?"
        description="Lakeshore Women's Soccer · Buenos Aires · Mar 7–16"
        footer={
          <>
            <Button variant="ghost" onClick={() => setDialog(false)}>
              Cancel
            </Button>
            <Button onClick={() => setDialog(false)}>Approve & send</Button>
          </>
        }
      >
        <p className="text-sm">The agent drafted a 10-day itinerary with 3 matches. Sending emails the coach a proposal link.</p>
      </Dialog>
      <Sheet open={sheet} onClose={() => setSheet(false)} title="Node run" description="draft_trip · succeeded in 2.4 s">
        <pre className="overflow-x-auto rounded-md bg-muted p-3 font-mono text-xs">{`{\n  "tripId": "trp_8f2c",\n  "matches": 3,\n  "pricePerPersonUsd": 2890\n}`}</pre>
      </Sheet>
    </div>
  );
}
