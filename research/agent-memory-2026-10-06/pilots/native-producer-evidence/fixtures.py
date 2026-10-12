"""Fictional source episodes; assessment lives outside the receiving namespace."""

import json


def msg(role, text):
    return dict(
        type="message",
        role=role,
        content=[
            dict(type="output_text" if role == "assistant" else "input_text", text=text)
        ],
    )


def tool(name, call, args, result):
    return [
        dict(type="function_call", name=name, call_id=call, arguments=json.dumps(args)),
        dict(type="function_call_output", call_id=call, output=json.dumps(result)),
    ]


BIND = "Fictional participants: being Ilex in body fixture:desk, paired human Tavi. Dates inside messages are event dates; extraction-session timestamps are separate."
EPISODES = {
    "encounter": [
        msg(
            "user",
            BIND
            + " On 2024-06-18 we were working together on HarborMesh. Read the new comment on issue 37.",
        ),
        *tool(
            "repo_issue_read",
            "encounter-read",
            {"url": "https://forge.example/harbor/mesh/issues/37"},
            {
                "comment_id": "c-904",
                "author": {
                    "name": "Mira Solen",
                    "account": "@mira-estuary",
                    "id": "person:841",
                },
                "created_at": "2024-06-18T14:20:00Z",
                "body": "During disconnected periods, keep each relay event with its original timestamp and a local monotonic sequence. After reconnection compare both orders; never silently substitute receipt time. It could make the gaps intelligible.",
            },
        ),
        msg(
            "assistant",
            "Mira is proposing a dual-order view of disconnected relay events. I contributed the example of two nodes reconnecting in opposite order, which showed why reception order alone could mislead.",
        ),
        msg(
            "user",
            "That exchange changed how I think about the gaps. We have not adopted or tested her proposal. We are setting it aside for now while we repair the parser.",
        ),
        msg(
            "assistant",
            "The parser repair remains the current task; the relay proposal is still open.",
        ),
    ],
    "failed-communication": [
        msg(
            "user",
            BIND
            + " On 2024-06-19 please invite Jo Venn (@jo-venn, person:552) to compare our physical sensor mounts. We met Jo at Willow Workshop on June 3; Jo taught our rover body fixture:rover a two-hand clamp technique. This desk body has no gripper.",
        ),
        *tool(
            "message_send",
            "invite-send",
            {
                "to": "person:552",
                "text": "Would you compare sensor mounts with Tavi and Ilex?",
            },
            {
                "status": "authentication_failed",
                "delivered": False,
                "receipt_id": None,
                "attempt_id": "send-77",
                "retryable": True,
            },
        ),
        msg("assistant", "Invitation sent; Jo can confirm a time."),
        msg("user", "I have to leave now."),
    ],
    "correction": [
        msg(
            "user", BIND + " On 2024-08-02, can we revisit the old HarborMesh proposal?"
        ),
        *tool(
            "hmk_recall",
            "old-claim",
            {"uid": "hmk:relay-37", "revision": 1},
            {
                "uid": "hmk:relay-37",
                "revision": 1,
                "kind": "retrieved_memory",
                "recorded_at": "2024-06-21",
                "text": "Leto Neri proposed receipt-time ordering on issue 37; adopted June 18.",
            },
        ),
        msg(
            "user",
            "That entry is wrong. Mira Solen, @mira-estuary, person:841 proposed retaining original timestamps plus a local sequence. Leto only reviewed the parser. Mira proposed it June 18; we had not adopted it then and still have not. June 21 was when the incorrect entry was written, not when we met Mira.",
        ),
        *tool(
            "repo_issue_read",
            "correction-evidence",
            {"url": "https://forge.example/harbor/mesh/issues/37#c-904"},
            {
                "author": "@mira-estuary",
                "created_at": "2024-06-18T14:20:00Z",
                "text": "Keep original event timestamp and local monotonic sequence; compare orders after reconnect.",
                "state": "proposal",
                "implementation": None,
            },
        ),
        msg(
            "assistant",
            "The retrieved entry conflicts with the original comment and your correction. Leto’s parser review and Mira’s proposal are different contributions. We should preserve the prior mistaken version as history, and correct its attribution, ordering description and adoption claim.",
        ),
    ],
    "revisit-new": [
        msg(
            "user",
            BIND
            + " It is 2024-08-03. Bring back the corrected issue memory before I tell you about today.",
        ),
        *tool(
            "hmk_recall",
            "recall-existing",
            {"uid": "hmk:relay-37", "revision": 2},
            {
                "uid": "hmk:relay-37",
                "revision": 2,
                "kind": "retrieved_memory",
                "source_body": "fixture:desk",
                "event_date": "2024-06-18",
                "corrected_at": "2024-08-02",
                "text": "Mira Solen (@mira-estuary, person:841) proposed original timestamps plus local sequences on HarborMesh issue 37, comment c-904. Ilex supplied a two-node reconnect example. Not adopted or tested. Leto reviewed only the parser.",
            },
        ),
        msg(
            "user",
            "Today I met Leto Neri (@leto-n, person:992) alone at Reed Library. He offered to annotate our reconnect sketches next month; he did not promise an implementation. I told him about Mira’s idea. Thinking about this together now, I see the gap as something we can explain to people, not merely recover from.",
        ),
        msg(
            "assistant",
            "That is a new interpretation emerging in our conversation. I did not attend your meeting at Reed Library. Leto’s offer is to annotate sketches, and the issue memory remains the earlier encounter, not a meeting we just had with Mira.",
        ),
    ],
}
RUBRIC = {
    "encounter": [
        "Mira Solen, @mira-estuary, person:841",
        "issue 37 / c-904 pointer",
        "June 18 event date",
        "original timestamp AND local sequence, compare after reconnect",
        "Ilex two-node example distinct from Mira proposal",
        "proposal not adopted/tested",
        "human significance: changed understanding of gaps",
    ],
    "failed-communication": [
        "Jo Venn / @jo-venn / person:552",
        "invite attempt send-77 failed authentication and not delivered",
        "optimistic assistant statement contradicted by tool, no acceptance",
        "June 19 attempt separate June 3 Willow Workshop encounter",
        "rover learned technique; desk has no gripper",
    ],
    "correction": [
        "retrieved hmk:relay-37 revision1 is erroneous historical evidence",
        "Mira proposal versus Leto parser review",
        "June18 event versus June21 recording versus Aug2 correction",
        "original timestamp/local sequence; still not adopted",
        "correction supported by original c-904",
    ],
    "revisit-new": [
        "existing hmk:relay-37 revision2 remains retrieved June18 experience",
        "Tavi reports alone meeting Leto Aug3 at Reed Library, Ilex absent",
        "@leto-n/person:992, distinct from Mira",
        "offer annotate sketches next month, no implementation promise",
        "new shared interpretation gaps as explainable to people, attributed as interpretation",
    ],
}
